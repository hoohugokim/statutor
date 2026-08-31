//! Conformance-gated Rust twin of the statutor git floor.
//!
//! Implements ONLY `staged` mode (local pre-commit/CI), byte-compatible
//! with `python3 core/statutor_core.py staged <dir>` — same exit codes, same
//! `STATUTOR  <violation>` lines, same Python-list-repr section formatting —
//! as a native binary that does not require a Python runtime. It does not
//! implement the ref-range semantics required by server-side pre-receive.
//!
//! Existence license (DECISIONS.md D-0014): this duplicate is allowed to
//! exist only while `tests/test_conformance_rust.py` proves Python ≡ Rust
//! on every scenario; divergence fails CI. The policy kernel stays
//! canonical in Python.

use std::path::{Path, PathBuf};
use std::process::Command;

/// One governed entry from `.statutor.yaml` (`pattern` + `policy` plus
/// optional sizing/section keys).
#[derive(Debug, Clone)]
pub struct Rule {
    pub pattern: String,
    pub policy: String,
    pub max_lines: Option<i64>,
    pub hard_max_lines: Option<i64>,
    pub required_sections: Vec<String>,
}

impl Rule {
    /// Line cap exactly as the kernel resolves it:
    /// `int(rule.get("max_lines", rule.get("hard_max_lines", 200)))`.
    fn cap(&self) -> i64 {
        self.max_lines.or(self.hard_max_lines).unwrap_or(200)
    }
}

#[derive(Debug, Clone)]
pub struct Policy {
    pub bash_guard: bool,
    pub governed: Vec<Rule>,
}

/// Byte-equivalent of DEFAULT_POLICY in core/statutor_core.py.
pub fn default_policy() -> Policy {
    Policy {
        bash_guard: true,
        governed: vec![
            Rule {
                pattern: "AGENTS.md".into(),
                policy: "constitution".into(),
                max_lines: None,
                hard_max_lines: Some(200),
                required_sections: vec![],
            },
            Rule {
                pattern: "HANDOFF.md".into(),
                policy: "overwrite_bounded".into(),
                max_lines: Some(40),
                hard_max_lines: None,
                required_sections: [
                    "## Goal",
                    "## Last verified state",
                    "## Next action",
                    "## Gotchas",
                    "## Do not touch",
                ]
                .iter()
                .map(|s| s.to_string())
                .collect(),
            },
            Rule {
                pattern: "DECISIONS.md".into(),
                policy: "append_only".into(),
                max_lines: None,
                hard_max_lines: None,
                required_sections: vec![],
            },
            Rule {
                pattern: "TASKS.md".into(),
                policy: "state".into(),
                max_lines: None,
                hard_max_lines: None,
                required_sections: vec![],
            },
            Rule {
                pattern: "plans/archive/*".into(),
                policy: "frozen".into(),
                max_lines: None,
                hard_max_lines: None,
                required_sections: vec![],
            },
        ],
    }
}

fn parse_policy(text: &str) -> Result<Policy, ()> {
    let docs = yaml_rust2::YamlLoader::load_from_str(text).map_err(|_| ())?;
    let doc = docs.into_iter().next().ok_or(())?;
    let root = doc.as_hash().ok_or(())?;
    for key in root.keys() {
        let key = key.as_str().ok_or(())?;
        if !matches!(key, "bash_guard" | "governed") {
            return Err(());
        }
    }
    let bash_guard = root
        .get(&yaml_rust2::Yaml::from_str("bash_guard"))
        .map(|value| value.as_bool().ok_or(()))
        .transpose()?
        .unwrap_or(true);
    let governed_key = &yaml_rust2::Yaml::from_str("governed");
    let governed = root.get(governed_key).ok_or(())?.as_vec().ok_or(())?;

    let mut rules = Vec::new();
    for item in governed {
        let map = item.as_hash().ok_or(())?;
        for key in map.keys() {
            let key = key.as_str().ok_or(())?;
            if !matches!(
                key,
                "pattern"
                    | "policy"
                    | "max_lines"
                    | "hard_max_lines"
                    | "soft_max_lines"
                    | "stale_after_days"
                    | "required_sections"
            ) {
                return Err(());
            }
        }
        let get_str = |k: &str| -> Option<String> {
            map.get(&yaml_rust2::Yaml::from_str(k))
                .and_then(|v| v.as_str())
                .map(|s| s.to_string())
        };
        let pattern = get_str("pattern").ok_or(())?;
        let policy = get_str("policy").ok_or(())?;
        if pattern.is_empty()
            || !matches!(
                policy.as_str(),
                "constitution" | "overwrite_bounded" | "append_only" | "state" | "frozen"
            )
        {
            return Err(());
        }
        let int_of = |k: &str| -> Result<Option<i64>, ()> {
            let Some(value) = map.get(&yaml_rust2::Yaml::from_str(k)) else {
                return Ok(None);
            };
            let parsed = value
                .as_i64()
                .or_else(|| value.as_str().and_then(|s| s.parse::<i64>().ok()))
                .ok_or(())?;
            if parsed < 0 {
                return Err(());
            }
            Ok(Some(parsed))
        };
        // Validate doctor-only numeric fields even though the staged binary
        // does not otherwise consume them.
        let _ = int_of("soft_max_lines")?;
        let _ = int_of("stale_after_days")?;
        let required_sections = match map.get(&yaml_rust2::Yaml::from_str("required_sections")) {
            None => Vec::new(),
            Some(value) => value
                .as_vec()
                .ok_or(())?
                .iter()
                .map(|item| {
                    item.as_str()
                        .filter(|s| !s.is_empty())
                        .map(str::to_string)
                        .ok_or(())
                })
                .collect::<Result<Vec<_>, _>>()?,
        };
        rules.push(Rule {
            pattern,
            policy,
            max_lines: int_of("max_lines")?,
            hard_max_lines: int_of("hard_max_lines")?,
            required_sections,
        });
    }
    Ok(Policy {
        bash_guard,
        governed: rules,
    })
}

/// First rule whose pattern matches the rel path or its basename —
/// statutor_core._match_rule semantics, including backslash normalization.
pub fn match_rule<'a>(rel_path: &str, policy: &'a Policy) -> Option<&'a Rule> {
    let rel = rel_path.replace('\\', "/");
    let base = rel.rsplit('/').next().unwrap_or("");
    policy
        .governed
        .iter()
        .find(|r| fnmatch(&r.pattern, &rel) || fnmatch(&r.pattern, base))
}

/// Python `fnmatch.fnmatch` (case-sensitive, POSIX) subset: `*`, `?`,
/// `[seq]`, `[a-z]`, `[!seq]`; every other character is literal. Iterative
/// glob matcher with single-star backtracking.
pub fn fnmatch(pattern: &str, name: &str) -> bool {
    let p: Vec<char> = pattern.chars().collect();
    let n: Vec<char> = name.chars().collect();
    glob_match(&p, &n)
}

fn glob_match(p: &[char], n: &[char]) -> bool {
    let (mut pi, mut ni) = (0usize, 0usize);
    let (mut star_p, mut star_n) = (None::<usize>, 0usize);
    while ni < n.len() {
        if pi < p.len() && (p[pi] == '?' || p[pi] == n[ni]) {
            pi += 1;
            ni += 1;
        } else if pi < p.len() && p[pi] == '*' {
            star_p = Some(pi);
            star_n = ni;
            pi += 1;
        } else if pi < p.len() && p[pi] == '[' {
            match class_match(p, pi, n[ni]) {
                ClassResult::Hit(next_pi) => {
                    pi = next_pi;
                    ni += 1;
                }
                ClassResult::Miss => match star_p {
                    Some(sp) => {
                        pi = sp + 1;
                        star_n += 1;
                        ni = star_n;
                    }
                    None => return false,
                },
                // Python's fnmatch.translate emits an unterminated '[' as a
                // LITERAL character — "[abc" matches the name "[abc".
                ClassResult::Unterminated => {
                    if n[ni] == '[' {
                        pi += 1;
                        ni += 1;
                    } else {
                        match star_p {
                            Some(sp) => {
                                pi = sp + 1;
                                star_n += 1;
                                ni = star_n;
                            }
                            None => return false,
                        }
                    }
                }
            }
        } else if let Some(sp) = star_p {
            pi = sp + 1;
            star_n += 1;
            ni = star_n;
        } else {
            return false;
        }
    }
    while pi < p.len() && p[pi] == '*' {
        pi += 1;
    }
    pi == p.len()
}

/// Outcome of matching one `[...]` class at p[open]=='[' against char `c`.
enum ClassResult {
    /// Char matched; index just past the closing ']'.
    Hit(usize),
    /// Well-formed class that did not match.
    Miss,
    /// No closing ']' — Python treats the '[' as a literal character.
    Unterminated,
}

fn class_match(p: &[char], open: usize, c: char) -> ClassResult {
    let mut i = open + 1;
    let negated = i < p.len() && (p[i] == '!' || p[i] == '^');
    if negated {
        i += 1;
    }
    let start = i;
    let mut hit = false;
    loop {
        if i >= p.len() {
            return ClassResult::Unterminated;
        }
        if p[i] == ']' && i > start {
            break;
        }
        if i + 2 < p.len() && p[i + 1] == '-' && p[i + 2] != ']' {
            if c >= p[i] && c <= p[i + 2] {
                hit = true;
            }
            i += 3;
        } else {
            if p[i] == c {
                hit = true;
            }
            i += 1;
        }
    }
    if hit != negated {
        ClassResult::Hit(i + 1)
    } else {
        ClassResult::Miss
    }
}

/// Exact Git stdout bytes or an actionable, parity-stable floor error.
fn git(cwd: &Path, args: &[&str]) -> Result<Vec<u8>, String> {
    let display = format!("git {}", args.join(" "));
    let output = Command::new("git")
        .arg("-c")
        .arg("color.ui=false")
        .args(args)
        .current_dir(cwd)
        .output()
        .map_err(|_| {
            format!(
                "{display} could not start; staged validation requires a non-bare \
Git worktree with a readable index."
            )
        })?;
    if !output.status.success() {
        let code = output
            .status
            .code()
            .map(|n| n.to_string())
            .unwrap_or_else(|| "unknown".to_string());
        return Err(format!(
            "{display} failed (exit {code}); staged validation requires a non-bare \
Git worktree with a readable index."
        ));
    }
    Ok(output.stdout)
}

fn git_optional(cwd: &Path, args: &[&str]) -> Result<Option<Vec<u8>>, String> {
    let display = format!("git {}", args.join(" "));
    let output = Command::new("git")
        .arg("-c")
        .arg("color.ui=false")
        .args(args)
        .current_dir(cwd)
        .output()
        .map_err(|_| format!("{display} could not start; trust state is unknown."))?;
    if output.status.success() {
        return Ok(Some(output.stdout));
    }
    if matches!(output.status.code(), Some(1 | 128)) {
        return Ok(None);
    }
    Err(format!("{display} failed; trust state is unknown."))
}

fn head_oid(cwd: &Path) -> Result<Option<String>, String> {
    Ok(
        git_optional(cwd, &["rev-parse", "--verify", "--quiet", "HEAD"])?
            .map(|raw| String::from_utf8_lossy(&raw).trim().to_string()),
    )
}

fn head_entry(cwd: &Path, path: &str) -> Result<Option<(String, Vec<u8>)>, String> {
    if head_oid(cwd)?.is_none() {
        return Ok(None);
    }
    let listing = git(cwd, &["ls-tree", "-z", "HEAD", "--", path])?;
    if listing.is_empty() {
        return Ok(None);
    }
    let records: Vec<&[u8]> = listing
        .split(|byte| *byte == 0)
        .filter(|record| !record.is_empty())
        .collect();
    if records.len() != 1 {
        return Err(format!("git ls-tree returned ambiguous entry for {path}."));
    }
    let Some(tab) = records[0].iter().position(|byte| *byte == b'\t') else {
        return Err(format!("git ls-tree returned ambiguous entry for {path}."));
    };
    let metadata = &records[0][..tab];
    let listed = &records[0][tab + 1..];
    let fields: Vec<&[u8]> = metadata.split(|byte| byte.is_ascii_whitespace()).collect();
    if fields.len() != 3 || listed != path.as_bytes() {
        return Err(format!("git ls-tree returned malformed entry for {path}."));
    }
    let oid = String::from_utf8_lossy(fields[2]).to_string();
    let blob = git(cwd, &["show", &format!("HEAD:{path}")])?;
    Ok(Some((oid, blob)))
}

fn index_entry(cwd: &Path, path: &str) -> Result<Option<(String, Vec<u8>)>, String> {
    let listing = git(cwd, &["ls-files", "--stage", "-z", "--", path])?;
    if listing.is_empty() {
        return Ok(None);
    }
    let records: Vec<&[u8]> = listing
        .split(|byte| *byte == 0)
        .filter(|record| !record.is_empty())
        .collect();
    if records.len() != 1 {
        return Err(format!("index has ambiguous or unmerged entry for {path}."));
    }
    let Some(tab) = records[0].iter().position(|byte| *byte == b'\t') else {
        return Err(format!("index has ambiguous or unmerged entry for {path}."));
    };
    let metadata = &records[0][..tab];
    let listed = &records[0][tab + 1..];
    let fields: Vec<&[u8]> = metadata.split(|byte| byte.is_ascii_whitespace()).collect();
    if fields.len() != 3 || fields[2] != b"0" || listed != path.as_bytes() {
        return Err(format!("index has malformed or unmerged entry for {path}."));
    }
    let oid = String::from_utf8_lossy(fields[1]).to_string();
    let blob = git(cwd, &["show", &format!(":{path}")])?;
    Ok(Some((oid, blob)))
}

#[derive(Debug)]
struct PolicySnapshots {
    baseline: Policy,
    candidate: Policy,
    baseline_policy_oid: Option<String>,
    candidate_policy_oid: Option<String>,
}

fn policy_snapshots(cwd: &Path) -> Result<PolicySnapshots, String> {
    let baseline_entry = head_entry(cwd, ".statutor.yaml")?;
    let candidate_entry = index_entry(cwd, ".statutor.yaml")?;
    let baseline = match &baseline_entry {
        None => default_policy(),
        Some((_, blob)) => parse_policy(&String::from_utf8_lossy(blob)).map_err(|_| {
            "HEAD:.statutor.yaml: invalid or unsupported Statutor policy".to_string()
        })?,
    };
    let candidate = match &candidate_entry {
        None => default_policy(),
        Some((_, blob)) => parse_policy(&String::from_utf8_lossy(blob))
            .map_err(|_| ":.statutor.yaml: invalid or unsupported Statutor policy".to_string())?,
    };
    Ok(PolicySnapshots {
        baseline,
        candidate,
        baseline_policy_oid: baseline_entry.map(|entry| entry.0),
        candidate_policy_oid: candidate_entry.map(|entry| entry.0),
    })
}

#[derive(Debug)]
struct Change {
    status: String,
    old: Option<String>,
    new: Option<String>,
}

fn staged_changes(cwd: &Path) -> Result<Vec<Change>, String> {
    let worktree = git(cwd, &["rev-parse", "--is-inside-work-tree"])?;
    if String::from_utf8_lossy(&worktree).trim() != "true" {
        return Err(
            "git rev-parse --is-inside-work-tree reported no worktree; staged \
validation requires a non-bare Git worktree with a readable index."
                .to_string(),
        );
    }

    let args = ["diff", "--cached", "--name-status", "-z", "-M"];
    let raw = git(cwd, &args)?;
    let mut fields: Vec<&[u8]> = raw.split(|b| *b == 0).collect();
    if fields.last().is_some_and(|field| field.is_empty()) {
        fields.pop();
    }
    let mut changes = Vec::new();
    let mut i = 0usize;
    while i < fields.len() {
        let status = String::from_utf8_lossy(fields[i]).into_owned();
        i += 1;
        let paths_needed = if status.starts_with('R') || status.starts_with('C') {
            2
        } else {
            1
        };
        if status.is_empty() || i + paths_needed > fields.len() {
            return Err(
                "git diff --cached --name-status -z -M returned malformed output; \
staged validation cannot safely identify changed paths."
                    .to_string(),
            );
        }
        let paths: Vec<String> = fields[i..i + paths_needed]
            .iter()
            .map(|p| String::from_utf8_lossy(p).into_owned())
            .collect();
        i += paths_needed;
        let code = status.as_bytes()[0] as char;
        let (old, new) = match code {
            'A' => (None, Some(paths[0].clone())),
            'D' => (Some(paths[0].clone()), None),
            'R' | 'C' => (Some(paths[0].clone()), Some(paths[1].clone())),
            _ => (Some(paths[0].clone()), Some(paths[0].clone())),
        };
        changes.push(Change { status, old, new });
    }
    Ok(changes)
}

fn frozen_msg(path: &str) -> String {
    format!(
        "{path}: frozen — archived records are immutable \
(moving a plan INTO the archive is allowed)."
    )
}

fn direct_frozen_add_msg(path: &str) -> String {
    format!(
        "{path}: frozen — direct additions to the archive are denied \
(move an existing plan INTO the archive instead)."
    )
}

fn lifecycle_msg(path: &str, kind: &str, destination: Option<&str>) -> String {
    match destination {
        None => format!(
            "{path}: governed ({kind}) record cannot be deleted; \
supersede it without removing its governed path."
        ),
        Some(dest) => format!(
            "{path}: governed ({kind}) record cannot move to ungoverned path \
{dest}; keep it under the same policy rule."
        ),
    }
}

fn lifecycle_policy(kind: &str) -> bool {
    matches!(
        kind,
        "constitution" | "overwrite_bounded" | "append_only" | "state"
    )
}

/// Python str repr with our realistic inputs (no embedded quotes): wrap in
/// single quotes. Byte-parity with f-string list formatting in run_staged.
fn py_repr(s: &str) -> String {
    format!("'{s}'")
}

fn py_list(items: &[String]) -> String {
    let quoted: Vec<String> = items.iter().map(|s| py_repr(s)).collect();
    format!("[{}]", quoted.join(", "))
}

const EXACT_CLAUDE_BRIDGES: [&[u8]; 2] = [b"@AGENTS.md\n", b"@AGENTS.md"];

fn reserved_changes(cwd: &Path, snapshots: &PolicySnapshots) -> Result<Vec<String>, String> {
    if snapshots.baseline_policy_oid.is_none() {
        return Ok(Vec::new());
    }
    let mut reserved = Vec::new();
    if snapshots.baseline_policy_oid != snapshots.candidate_policy_oid {
        reserved.push(".statutor.yaml".to_string());
    }
    let baseline = head_entry(cwd, "CLAUDE.md")?.map(|entry| entry.1);
    let candidate = index_entry(cwd, "CLAUDE.md")?.map(|entry| entry.1);
    let baseline_exact = baseline
        .as_deref()
        .is_some_and(|blob| EXACT_CLAUDE_BRIDGES.contains(&blob));
    let candidate_exact = candidate
        .as_deref()
        .is_some_and(|blob| EXACT_CLAUDE_BRIDGES.contains(&blob));
    if (baseline_exact && baseline != candidate) || (!baseline_exact && candidate_exact) {
        reserved.push("CLAUDE.md".to_string());
    }
    reserved.sort();
    Ok(reserved)
}

fn git_local_path(cwd: &Path, relative: &str) -> Result<PathBuf, String> {
    let raw = git(cwd, &["rev-parse", "--git-path", relative])?;
    let raw = String::from_utf8_lossy(&raw).trim().to_string();
    let path = PathBuf::from(raw);
    Ok(if path.is_absolute() {
        path
    } else {
        cwd.join(path)
    })
}

#[derive(Debug)]
struct TrustContext {
    repo_identity: String,
    head_oid: Option<String>,
    index_tree_oid: String,
    baseline_policy_oid: Option<String>,
    candidate_policy_oid: Option<String>,
    approved_reserved_paths: Vec<String>,
}

fn trust_context(
    cwd: &Path,
    snapshots: &PolicySnapshots,
    reserved: &[String],
) -> Result<TrustContext, String> {
    let raw = git(cwd, &["rev-parse", "--git-common-dir"])?;
    let common = PathBuf::from(String::from_utf8_lossy(&raw).trim().to_string());
    let common = if common.is_absolute() {
        common
    } else {
        cwd.join(common)
    };
    let repo_identity = std::fs::canonicalize(common)
        .map_err(|_| {
            "git common directory could not be resolved; trust state is unknown.".to_string()
        })?
        .to_string_lossy()
        .to_string();
    Ok(TrustContext {
        repo_identity,
        head_oid: head_oid(cwd)?,
        index_tree_oid: String::from_utf8_lossy(&git(cwd, &["write-tree"])?)
            .trim()
            .to_string(),
        baseline_policy_oid: snapshots.baseline_policy_oid.clone(),
        candidate_policy_oid: snapshots.candidate_policy_oid.clone(),
        approved_reserved_paths: reserved.to_vec(),
    })
}

fn yaml_string<'a>(map: &'a yaml_rust2::yaml::Hash, key: &str) -> Option<&'a str> {
    map.get(&yaml_rust2::Yaml::from_str(key))?.as_str()
}

fn yaml_optional_string(map: &yaml_rust2::yaml::Hash, key: &str) -> Result<Option<String>, ()> {
    let value = map.get(&yaml_rust2::Yaml::from_str(key)).ok_or(())?;
    if value.is_null() {
        Ok(None)
    } else {
        Ok(Some(value.as_str().ok_or(())?.to_string()))
    }
}

fn receipt_authorizes(cwd: &Path, expected: &TrustContext) -> bool {
    let Ok(path) = git_local_path(cwd, "statutor/trust-receipt.json") else {
        return false;
    };
    let Ok(metadata) = std::fs::symlink_metadata(&path) else {
        return false;
    };
    if metadata.file_type().is_symlink() {
        return false;
    }
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        if metadata.permissions().mode() & 0o777 != 0o600 {
            return false;
        }
    }
    let Ok(text) = std::fs::read_to_string(path) else {
        return false;
    };
    let Ok(docs) = yaml_rust2::YamlLoader::load_from_str(&text) else {
        return false;
    };
    let Some(map) = docs.first().and_then(|doc| doc.as_hash()) else {
        return false;
    };
    let version = map
        .get(&yaml_rust2::Yaml::from_str("version"))
        .and_then(|value| value.as_i64());
    if version != Some(1)
        || yaml_string(map, "repo_identity") != Some(expected.repo_identity.as_str())
        || yaml_string(map, "index_tree_oid") != Some(expected.index_tree_oid.as_str())
        || yaml_optional_string(map, "head_oid").ok() != Some(expected.head_oid.clone())
        || yaml_optional_string(map, "baseline_policy_oid").ok()
            != Some(expected.baseline_policy_oid.clone())
        || yaml_optional_string(map, "candidate_policy_oid").ok()
            != Some(expected.candidate_policy_oid.clone())
    {
        return false;
    }
    let Some(paths) = map
        .get(&yaml_rust2::Yaml::from_str("approved_reserved_paths"))
        .and_then(|value| value.as_vec())
    else {
        return false;
    };
    let actual_paths: Option<Vec<String>> = paths
        .iter()
        .map(|value| value.as_str().map(str::to_string))
        .collect();
    if actual_paths.as_deref() != Some(expected.approved_reserved_paths.as_slice()) {
        return false;
    }
    let Some(decision) = yaml_string(map, "decision") else {
        return false;
    };
    let valid_decision = decision
        .strip_prefix("D-")
        .is_some_and(|digits| digits.len() >= 4 && digits.chars().all(|ch| ch.is_ascii_digit()));
    valid_decision && yaml_string(map, "reason").is_some_and(|reason| !reason.trim().is_empty())
}

fn line_count(blob: &str) -> i64 {
    if blob.is_empty() {
        0
    } else {
        blob.matches('\n').count() as i64 + i64::from(!blob.ends_with('\n'))
    }
}

fn pure_line_insertion(before: &[u8], after: &[u8]) -> bool {
    let original: Vec<&[u8]> = before.split_inclusive(|b| *b == b'\n').collect();
    if original.is_empty() {
        return true;
    }
    let mut matched = 0usize;
    for candidate in after.split_inclusive(|b| *b == b'\n') {
        if candidate == original[matched] {
            matched += 1;
            if matched == original.len() {
                return true;
            }
        }
    }
    false
}

fn staged_violations(cwd: &Path, policy: &Policy) -> Result<Vec<String>, String> {
    let changes = staged_changes(cwd)?;
    let mut violations = Vec::new();

    // Pass 1 — governed-record lifecycle and frozen transitions.
    for change in &changes {
        let code = change.status.as_bytes()[0] as char;
        let old_rule = change.old.as_deref().and_then(|p| match_rule(p, policy));
        let new_rule = change.new.as_deref().and_then(|p| match_rule(p, policy));
        let old_kind = old_rule.map(|r| r.policy.as_str()).unwrap_or("");
        let new_kind = new_rule.map(|r| r.policy.as_str()).unwrap_or("");

        if code == 'D' {
            let old = change.old.as_deref().unwrap_or("");
            if old_kind == "frozen" {
                violations.push(frozen_msg(old));
            } else if lifecycle_policy(old_kind) {
                violations.push(lifecycle_msg(old, old_kind, None));
            }
            continue;
        }

        if code == 'R' {
            let old = change.old.as_deref().unwrap_or("");
            let new = change.new.as_deref().unwrap_or("");
            if old_kind == "frozen" {
                violations.push(frozen_msg(old));
            } else if lifecycle_policy(old_kind)
                && !matches!((old_rule, new_rule), (Some(a), Some(b)) if std::ptr::eq(a, b))
            {
                violations.push(lifecycle_msg(old, old_kind, Some(new)));
            }
            // A rename is the sole supported way to arrive in frozen.
            continue;
        }

        if new_kind == "frozen" {
            let new = change.new.as_deref().unwrap_or("");
            if code == 'A' || code == 'C' {
                violations.push(direct_frozen_add_msg(new));
            } else {
                violations.push(frozen_msg(new));
            }
        }
    }

    // Pass 2 — candidate blob policies; deleted paths have no candidate.
    for change in &changes {
        let Some(path) = change.new.as_deref() else {
            continue;
        };
        let Some(rule) = match_rule(path, policy) else {
            continue;
        };
        let code = change.status.as_bytes()[0] as char;
        match rule.policy.as_str() {
            "append_only" => {
                let old_rule = change.old.as_deref().and_then(|p| match_rule(p, policy));
                let same_rule = matches!(old_rule, Some(old) if std::ptr::eq(old, rule));
                let baseline = if matches!(code, 'M' | 'T') || (code == 'R' && same_rule) {
                    let old = change.old.as_deref().unwrap_or("");
                    git(cwd, &["show", &format!("HEAD:{old}")])?
                } else {
                    Vec::new()
                };
                let candidate = git(cwd, &["show", &format!(":{path}")])?;
                if !pure_line_insertion(&baseline, &candidate) {
                    violations.push(format!(
                        "{path}: append-only, but staged content deletes, rewrites, \
or reorders existing lines. Append superseding records instead."
                    ));
                }
            }
            "overwrite_bounded" | "constitution" => {
                let bytes = git(cwd, &["show", &format!(":{path}")])?;
                let blob = String::from_utf8_lossy(&bytes);
                let n = line_count(&blob);
                let cap = rule.cap();
                if n > cap {
                    violations.push(format!("{path}: staged version is {n} lines (cap {cap})."));
                }
                let missing: Vec<String> = rule
                    .required_sections
                    .iter()
                    .filter(|s| !blob.contains(s.as_str()))
                    .cloned()
                    .collect();
                if !missing.is_empty() {
                    violations.push(format!("{path}: missing sections {}.", py_list(&missing)));
                }
            }
            _ => {}
        }
    }
    Ok(violations)
}

/// The floor itself: validate the staged changes in `cwd`. Returns
/// (exit_code, stdout) byte-compatible with the Python kernel's staged mode.
pub fn run_staged(cwd: &Path) -> (i32, String) {
    let violations = match (|| -> Result<Vec<String>, String> {
        // Validate repository/index before resolving the two policy snapshots.
        let _ = staged_changes(cwd)?;
        let snapshots = policy_snapshots(cwd)?;
        let reserved = reserved_changes(cwd, &snapshots)?;
        let mut violations = Vec::new();
        if !reserved.is_empty() {
            let context = trust_context(cwd, &snapshots, &reserved)?;
            if !receipt_authorizes(cwd, &context) {
                violations.push(format!(
                    "trust-root change requires `statutor trust approve --decision \
D-NNNN --reason TEXT`; missing, stale, or unsafe receipt for {}.",
                    py_list(&reserved)
                ));
            }
        }
        for policy in [&snapshots.baseline, &snapshots.candidate] {
            for violation in staged_violations(cwd, policy)? {
                if !violations.contains(&violation) {
                    violations.push(violation);
                }
            }
        }
        Ok(violations)
    })() {
        Ok(v) => v,
        Err(reason) => return (1, format!("STATUTOR  {reason}\n")),
    };

    let stdout = violations
        .iter()
        .map(|v| format!("STATUTOR  {v}"))
        .collect::<Vec<_>>()
        .join("\n");
    let stdout = if violations.is_empty() {
        String::new()
    } else {
        format!("{stdout}\n")
    };
    let code = if violations.is_empty() { 0 } else { 1 };
    (code, stdout)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn fnmatch_star_question_classes() {
        assert!(fnmatch("plans/archive/*", "plans/archive/a.md"));
        assert!(fnmatch("plans/archive/*", "plans/archive/sub/deep.md"));
        assert!(!fnmatch("plans/archive/*", "plans/active.md"));
        assert!(fnmatch("AGENTS.md", "AGENTS.md"));
        assert!(!fnmatch("AGENTS.md", "AGENTS.md.bak"));
        assert!(fnmatch("h?llo", "hello"));
        assert!(!fnmatch("h?llo", "heello"));
        assert!(fnmatch("[abc]at", "bat"));
        assert!(!fnmatch("[abc]at", "dat"));
        assert!(fnmatch("[a-z]at", "mat"));
        assert!(fnmatch("[!a-z]at", "3at"));
        assert!(!fnmatch("[!a-z]at", "bat"));
        assert!(fnmatch("a*b*c", "aXXbYYc"));
        assert!(fnmatch("a*b*c", "abc"));
        assert!(!fnmatch("a*b*c", "aXbX"));
        // unterminated class: python emits the '[' as a literal char
        assert!(fnmatch("[abc", "[abc"));
        assert!(!fnmatch("[abc", "x[abc"));
    }

    #[test]
    fn policy_parse_and_fallback() {
        let ok = parse_policy("governed:\n  - pattern: X.md\n    policy: append_only\n").unwrap();
        assert_eq!(ok.governed[0].pattern, "X.md");
        let sized = parse_policy(
            "governed:\n  - pattern: H.md\n    policy: overwrite_bounded\n    max_lines: 9\n",
        )
        .unwrap();
        assert_eq!(sized.governed[0].cap(), 9);
        let quoted = parse_policy(
            "governed:\n  - pattern: H.md\n    policy: overwrite_bounded\n    max_lines: \"9\"\n",
        )
        .unwrap();
        assert_eq!(quoted.governed[0].cap(), 9);
        let backstop =
            parse_policy("governed:\n  - pattern: A.md\n    policy: constitution\n").unwrap();
        assert_eq!(backstop.governed[0].cap(), 200);
        // malformed / missing governed key / non-mapping → None → caller falls back
        assert!(parse_policy("::: broken [").is_err());
        assert!(parse_policy("bash_guard: false\n").is_err());
        assert!(parse_policy("- just\n- a list\n").is_err());
    }

    #[test]
    fn default_policy_governs_expected_paths() {
        let p = default_policy();
        assert_eq!(
            match_rule("docs/DECISIONS.md", &p).unwrap().policy,
            "append_only"
        );
        assert_eq!(
            match_rule("plans/archive/x.md", &p).unwrap().policy,
            "frozen"
        );
        assert!(match_rule("src/main.rs", &p).is_none());
        assert_eq!(
            match_rule("plans\\archive\\win.md", &p).unwrap().policy,
            "frozen"
        );
    }

    #[test]
    fn py_list_repr_matches_python_formatting() {
        assert_eq!(
            py_list(&["## Gotchas".into(), "## Do not touch".into()]),
            "['## Gotchas', '## Do not touch']"
        );
    }

    #[test]
    fn append_only_uses_byte_exact_line_subsequence() {
        let before = b"first\nsecond\n";
        assert!(pure_line_insertion(before, b"first\ninserted\nsecond\n"));
        assert!(!pure_line_insertion(before, b"first\nchanged\n"));
        assert!(!pure_line_insertion(b"last line", b"last line\nnew\n"));
        assert!(!pure_line_insertion(before, b"rewritten\0binary\n"));
    }

    #[test]
    fn physical_line_count_ignores_trailing_lf_sentinel() {
        assert_eq!(line_count(""), 0);
        assert_eq!(line_count("one"), 1);
        assert_eq!(line_count("one\n"), 1);
        assert_eq!(line_count("one\ntwo\n"), 2);
    }
}
