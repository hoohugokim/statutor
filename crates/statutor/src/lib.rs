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

use std::path::Path;
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
    pub governed: Vec<Rule>,
}

/// Byte-equivalent of DEFAULT_POLICY in core/statutor_core.py.
pub fn default_policy() -> Policy {
    Policy {
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

/// Load `<cwd>/.statutor.yaml`, falling back to the embedded defaults on
/// absence, parse failure, or a document without a `governed` key — the
/// exact fallback contract of statutor_core.load_policy.
pub fn load_policy(cwd: &Path) -> Policy {
    let path = cwd.join(".statutor.yaml");
    let text = match std::fs::read_to_string(&path) {
        Ok(t) => t,
        Err(_) => return default_policy(),
    };
    match parse_policy(&text) {
        Some(p) => p,
        None => default_policy(),
    }
}

fn parse_policy(text: &str) -> Option<Policy> {
    let docs = yaml_rust2::YamlLoader::load_from_str(text).ok()?;
    let doc = docs.into_iter().next()?;
    let root = doc.as_hash()?;
    let governed_key = &yaml_rust2::Yaml::from_str("governed");
    let governed = root.get(governed_key)?.as_vec()?;

    let mut rules = Vec::new();
    for item in governed {
        let map = item.as_hash()?;
        let get_str = |k: &str| -> Option<String> {
            map.get(&yaml_rust2::Yaml::from_str(k))
                .and_then(|v| v.as_str())
                .map(|s| s.to_string())
        };
        let pattern = get_str("pattern").unwrap_or_default();
        let policy = get_str("policy").unwrap_or_default();
        let int_of = |k: &str| -> Option<i64> {
            map.get(&yaml_rust2::Yaml::from_str(k))
                .and_then(|v| v.as_i64())
        };
        let required_sections = map
            .get(&yaml_rust2::Yaml::from_str("required_sections"))
            .and_then(|v| v.as_vec())
            .map(|seq| {
                seq.iter()
                    .filter_map(|v| v.as_str().map(|s| s.to_string()))
                    .collect()
            })
            .unwrap_or_default();
        rules.push(Rule {
            pattern,
            policy,
            max_lines: int_of("max_lines"),
            hard_max_lines: int_of("hard_max_lines"),
            required_sections,
        });
    }
    Some(Policy { governed: rules })
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

fn line_count(blob: &str) -> i64 {
    blob.matches('\n').count() as i64 + 1
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
    let policy = load_policy(cwd);
    let violations = match staged_violations(cwd, &policy) {
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
        let backstop =
            parse_policy("governed:\n  - pattern: A.md\n    policy: constitution\n").unwrap();
        assert_eq!(backstop.governed[0].cap(), 200);
        // malformed / missing governed key / non-mapping → None → caller falls back
        assert!(parse_policy("::: broken [").is_none());
        assert!(parse_policy("bash_guard: false\n").is_none());
        assert!(parse_policy("- just\n- a list\n").is_none());
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
}
