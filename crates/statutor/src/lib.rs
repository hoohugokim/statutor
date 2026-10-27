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

use std::collections::{HashMap, HashSet};
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

#[derive(Debug)]
enum PolicyValue {
    Text(String),
    Integer(String),
    Boolean(bool),
    Sections(Vec<String>),
}

fn python_whitespace(c: char) -> bool {
    c.is_whitespace() || matches!(c, '\u{1c}'..='\u{1f}')
}

fn python_lines(mut text: &str) -> impl Iterator<Item = &str> {
    std::iter::from_fn(move || {
        if text.is_empty() {
            return None;
        }
        if let Some((index, c)) = text.char_indices().find(|&(_, c)| {
            matches!(
                c,
                '\n' | '\r' | '\u{b}' | '\u{c}' | '\u{1c}'
                    ..='\u{1e}' | '\u{85}' | '\u{2028}' | '\u{2029}'
            )
        }) {
            let line = &text[..index];
            let mut next = index + c.len_utf8();
            if c == '\r' && text[next..].starts_with('\n') {
                next += 1;
            }
            text = &text[next..];
            Some(line)
        } else {
            let line = text;
            text = "";
            Some(line)
        }
    })
}

fn decimal_integer(text: &str) -> Option<String> {
    // Unicode 16.0 Nd blocks, generated from the Python 3.14 canonical baseline.
    const STARTS: &[u32] = &[
        0x30, 0x660, 0x6f0, 0x7c0, 0x966, 0x9e6, 0xa66, 0xae6, 0xb66, 0xbe6, 0xc66, 0xce6, 0xd66,
        0xde6, 0xe50, 0xed0, 0xf20, 0x1040, 0x1090, 0x17e0, 0x1810, 0x1946, 0x19d0, 0x1a80, 0x1a90,
        0x1b50, 0x1bb0, 0x1c40, 0x1c50, 0xa620, 0xa8d0, 0xa900, 0xa9d0, 0xa9f0, 0xaa50, 0xabf0,
        0xff10, 0x104a0, 0x10d30, 0x10d40, 0x11066, 0x110f0, 0x11136, 0x111d0, 0x112f0, 0x11450,
        0x114d0, 0x11650, 0x116c0, 0x116d0, 0x116da, 0x11730, 0x118e0, 0x11950, 0x11bf0, 0x11c50,
        0x11d50, 0x11da0, 0x11f50, 0x16130, 0x16a60, 0x16ac0, 0x16b50, 0x16d70, 0x1ccf0, 0x1d7ce,
        0x1d7d8, 0x1d7e2, 0x1d7ec, 0x1d7f6, 0x1e140, 0x1e2f0, 0x1e4f0, 0x1e5f1, 0x1e950, 0x1fbf0,
    ];
    let (negative, digits) = if let Some(rest) = text.strip_prefix('-') {
        (true, rest)
    } else {
        (false, text.strip_prefix('+').unwrap_or(text))
    };
    if digits.is_empty() {
        return None;
    }
    let mut normalized = String::new();
    for c in digits.chars() {
        let cp = c as u32;
        let start = STARTS.iter().find(|&&base| cp >= base && cp < base + 10)?;
        normalized.push(char::from_digit(cp - start, 10)?);
    }
    let value = normalized.trim_start_matches('0');
    Some(if value.is_empty() {
        "0".into()
    } else if negative {
        format!("-{value}")
    } else {
        value.into()
    })
}

fn json_string(token: &str) -> Result<String, ()> {
    let mut chars = token.chars();
    if chars.next() != Some('"') {
        return Err(());
    }
    let mut value = String::new();
    while let Some(c) = chars.next() {
        match c {
            '"' => {
                return if chars.next().is_none() {
                    Ok(value)
                } else {
                    Err(())
                }
            }
            '\\' => match chars.next().ok_or(())? {
                '"' => value.push('"'),
                '\\' => value.push('\\'),
                '/' => value.push('/'),
                'b' => value.push('\u{8}'),
                'f' => value.push('\u{c}'),
                'n' => value.push('\n'),
                'r' => value.push('\r'),
                't' => value.push('\t'),
                'u' => {
                    let hex = |chars: &mut std::str::Chars<'_>| -> Result<u32, ()> {
                        let mut n = 0;
                        for _ in 0..4 {
                            n = n * 16 + chars.next().and_then(|c| c.to_digit(16)).ok_or(())?;
                        }
                        Ok(n)
                    };
                    let mut cp = hex(&mut chars)?;
                    if (0xd800..=0xdbff).contains(&cp) {
                        if chars.next() != Some('\\') || chars.next() != Some('u') {
                            return Err(());
                        }
                        let low = hex(&mut chars)?;
                        if !(0xdc00..=0xdfff).contains(&low) {
                            return Err(());
                        }
                        cp = 0x10000 + (cp - 0xd800) * 0x400 + low - 0xdc00;
                    }
                    value.push(char::from_u32(cp).ok_or(())?);
                }
                _ => return Err(()),
            },
            c if c < '\u{20}' => return Err(()),
            c => value.push(c),
        }
    }
    Err(())
}

fn policy_scalar(token: &str) -> Result<PolicyValue, ()> {
    let token = token.trim_matches(python_whitespace);
    if token.is_empty() {
        return Err(());
    }
    if token.starts_with('"') {
        return Ok(PolicyValue::Text(json_string(token)?));
    }
    if token.starts_with('\'') {
        if token.len() < 2 || !token.ends_with('\'') {
            return Err(());
        }
        return Ok(PolicyValue::Text(
            token[1..token.len() - 1].replace("''", "'"),
        ));
    }
    if token.eq_ignore_ascii_case("true") {
        return Ok(PolicyValue::Boolean(true));
    }
    if token.eq_ignore_ascii_case("false") {
        return Ok(PolicyValue::Boolean(false));
    }
    if token == "[]" {
        return Ok(PolicyValue::Sections(Vec::new()));
    }
    if let Some(number) = decimal_integer(token) {
        return Ok(PolicyValue::Integer(number));
    }
    if "[{&*!|>@`".contains(token.chars().next().ok_or(())?)
        || matches!(token, "null" | "Null" | "NULL" | "~")
    {
        return Err(());
    }
    Ok(PolicyValue::Text(token.into()))
}

fn strip_policy_comment(line: &str) -> &str {
    let mut quote = None;
    let mut escaped = false;
    let mut previous = None;
    for (i, c) in line.char_indices() {
        if escaped {
            escaped = false;
            previous = Some(c);
            continue;
        }
        if quote == Some('"') && c == '\\' {
            escaped = true;
            previous = Some(c);
            continue;
        }
        if matches!(c, '\'' | '"') {
            if quote.is_none() {
                quote = Some(c);
            } else if quote == Some(c) {
                quote = None;
            }
        } else if c == '#' && quote.is_none() && previous.map_or(true, python_whitespace) {
            return line[..i].trim_end_matches(python_whitespace);
        }
        previous = Some(c);
    }
    line.trim_end_matches(python_whitespace)
}

fn policy_mapping(text: &str) -> Result<(&str, &str), ()> {
    let (key, value) = text.split_once(':').ok_or(())?;
    let key = key.trim_matches(python_whitespace);
    if key.is_empty() || !key.chars().all(|c| c.is_ascii_lowercase() || c == '_') {
        return Err(());
    }
    Ok((key, value.trim_matches(python_whitespace)))
}

fn parse_policy(text: &str) -> Result<Policy, ()> {
    let mut top = HashMap::new();
    let mut fields: Vec<HashMap<String, PolicyValue>> = Vec::new();
    let mut current = None;
    let mut sections = false;
    for raw in python_lines(text) {
        if raw
            .chars()
            .take_while(|&c| python_whitespace(c))
            .any(|c| c == '\t')
        {
            return Err(());
        }
        let line = strip_policy_comment(raw);
        if line.trim_matches(python_whitespace).is_empty() {
            continue;
        }
        let indent = line.bytes().take_while(|&c| c == b' ').count();
        let body = &line[indent..];
        if indent == 0 {
            current = None;
            sections = false;
            let (key, token) = policy_mapping(body)?;
            if !matches!(key, "bash_guard" | "governed") || top.contains_key(key) {
                return Err(());
            }
            let value = if key == "governed" && token.is_empty() {
                PolicyValue::Sections(Vec::new())
            } else {
                policy_scalar(token)?
            };
            if !matches!(
                (&value, key),
                (PolicyValue::Boolean(_), "bash_guard") | (PolicyValue::Sections(_), "governed")
            ) {
                return Err(());
            }
            top.insert(key.to_string(), value);
            continue;
        }
        if !top.contains_key("governed") {
            return Err(());
        }
        let (key, token) = if indent == 2 && body.starts_with("- ") {
            fields.push(HashMap::new());
            current = Some(fields.len() - 1);
            sections = false;
            policy_mapping(&body[2..])?
        } else if indent == 4 && current.is_some() {
            sections = false;
            policy_mapping(body)?
        } else if indent == 6 && body.starts_with("- ") && sections {
            let PolicyValue::Text(value) = policy_scalar(&body[2..])? else {
                return Err(());
            };
            let Some(PolicyValue::Sections(items)) =
                fields[current.ok_or(())?].get_mut("required_sections")
            else {
                return Err(());
            };
            items.push(value);
            continue;
        } else {
            return Err(());
        };
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
        let map = &mut fields[current.ok_or(())?];
        if map.contains_key(key) {
            return Err(());
        }
        let value = if key == "required_sections" {
            sections = true;
            if token.is_empty() {
                PolicyValue::Sections(Vec::new())
            } else {
                let value = policy_scalar(token)?;
                if !matches!(value, PolicyValue::Sections(_)) {
                    return Err(());
                }
                value
            }
        } else {
            policy_scalar(token)?
        };
        map.insert(key.to_string(), value);
    }
    if !top.contains_key("governed") {
        return Err(());
    }
    let bash_guard = match top.get("bash_guard") {
        Some(PolicyValue::Boolean(value)) => *value,
        _ => true,
    };
    let mut governed = Vec::new();
    for map in fields {
        let text_of = |key| match map.get(key) {
            Some(PolicyValue::Text(value)) if !value.is_empty() => Ok(value.clone()),
            _ => Err(()),
        };
        let pattern = text_of("pattern")?;
        let policy = text_of("policy")?;
        if !matches!(
            policy.as_str(),
            "constitution" | "overwrite_bounded" | "append_only" | "state" | "frozen"
        ) {
            return Err(());
        }
        let integer_of = |key| -> Result<Option<i64>, ()> {
            let number = match map.get(key) {
                None => return Ok(None),
                Some(PolicyValue::Integer(value)) => value.clone(),
                Some(PolicyValue::Text(value)) => decimal_integer(value).ok_or(())?,
                _ => return Err(()),
            };
            if number.starts_with('-') {
                return Err(());
            }
            // A Git blob cannot contain more than i64::MAX physical lines.
            Ok(Some(number.bytes().fold(0_i64, |n, digit| {
                n.saturating_mul(10).saturating_add((digit - b'0') as i64)
            })))
        };
        integer_of("soft_max_lines")?;
        integer_of("stale_after_days")?;
        let required_sections = match map.get("required_sections") {
            None => Vec::new(),
            Some(PolicyValue::Sections(values)) if values.iter().all(|s| !s.is_empty()) => {
                values.clone()
            }
            _ => return Err(()),
        };
        governed.push(Rule {
            pattern,
            policy,
            max_lines: integer_of("max_lines")?,
            hard_max_lines: integer_of("hard_max_lines")?,
            required_sections,
        });
    }
    Ok(Policy {
        bash_guard,
        governed,
    })
}

/// First rule whose pattern matches the rel path or its basename —
/// statutor_core._match_rule semantics, including backslash normalization.
///
/// When `root` is set, a case-variant path matches only if it is the same
/// directory entry as a spelling the pattern already accepts. Patterns
/// themselves stay case-sensitive.
pub fn match_rule<'a>(
    rel_path: &str,
    policy: &'a Policy,
    root: Option<&Path>,
) -> Option<&'a Rule> {
    let rel = rel_path.replace(std::path::MAIN_SEPARATOR, "/");
    if let Some(rule) = match_rule_text(&rel, policy) {
        return Some(rule);
    }
    let root = root?;
    let stored = stored_rel_path(root, &rel)?;
    if stored == rel {
        return None;
    }
    match_rule_text(&stored, policy)
}

fn match_rule_text<'a>(rel: &str, policy: &'a Policy) -> Option<&'a Rule> {
    let base = rel.rsplit('/').next().unwrap_or("");
    policy
        .governed
        .iter()
        .find(|r| fnmatch(&r.pattern, rel) || fnmatch(&r.pattern, base))
}

fn same_file(left: &Path, right: &Path) -> bool {
    #[cfg(unix)]
    {
        use std::os::unix::fs::MetadataExt;
        let Ok(left) = std::fs::metadata(left) else {
            return false;
        };
        let Ok(right) = std::fs::metadata(right) else {
            return false;
        };
        return left.dev() == right.dev() && left.ino() == right.ino();
    }
    #[cfg(windows)]
    {
        use std::os::windows::fs::MetadataExt;
        let Ok(left) = std::fs::metadata(left) else {
            return false;
        };
        let Ok(right) = std::fs::metadata(right) else {
            return false;
        };
        return left.volume_serial_number() == right.volume_serial_number()
            && left.file_index() == right.file_index();
    }
    #[cfg(not(any(unix, windows)))]
    {
        let _ = (left, right);
        false
    }
}

fn stored_rel_path(root: &Path, rel_path: &str) -> Option<String> {
    if rel_path.starts_with('/') || rel_path.contains('\0') {
        return None;
    }
    let absolute = root.join(rel_path);
    if !absolute.exists() {
        return None;
    }
    let parent = absolute.parent()?;
    let mut matches = Vec::new();
    for entry in std::fs::read_dir(parent).ok()?.flatten() {
        let Some(name) = entry.file_name().to_str().map(str::to_string) else {
            continue;
        };
        if same_file(&entry.path(), &absolute) {
            matches.push(name);
            if matches.len() > 1 {
                return None;
            }
        }
    }
    let stored = matches.pop()?;
    match rel_path.rsplit_once('/') {
        Some((parent_rel, _)) if !parent_rel.is_empty() => Some(format!("{parent_rel}/{stored}")),
        _ => Some(stored),
    }
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
        if pi < p.len() && (p[pi] == '?' || (!matches!(p[pi], '*' | '[') && p[pi] == n[ni])) {
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
    let start = open + 1;
    let negated = p.get(start) == Some(&'!');
    let mut end = start + usize::from(negated);
    if p.get(end) == Some(&']') {
        end += 1;
    }
    while end < p.len() && p[end] != ']' {
        end += 1;
    }
    if end == p.len() {
        return ClassResult::Unterminated;
    }
    let mut chunks: Vec<Vec<char>> = Vec::new();
    let mut left = start;
    let mut scan = start + if negated { 2 } else { 1 };
    while scan < end {
        if p[scan] == '-' {
            chunks.push(p[left..scan].to_vec());
            left = scan + 1;
            scan += 3;
        } else {
            scan += 1;
        }
    }
    if left < end {
        chunks.push(p[left..end].to_vec());
    } else if let Some(last) = chunks.last_mut() {
        last.push('-');
    }
    for index in (1..chunks.len()).rev() {
        if chunks[index - 1].last() > chunks[index].first() {
            let tail = chunks.remove(index);
            chunks[index - 1].pop();
            chunks[index - 1].extend_from_slice(&tail[1..]);
        }
    }
    let negated = chunks.first().and_then(|part| part.first()) == Some(&'!');
    if negated {
        chunks[0].remove(0);
    }
    let hit = chunks.iter().any(|part| part.contains(&c)) || chunks.windows(2).any(|parts| {
        matches!((parts[0].last(), parts[1].first()), (Some(low), Some(high)) if low <= &c && &c <= high)
    });
    if hit != negated {
        ClassResult::Hit(end + 1)
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

#[derive(Debug, PartialEq)]
struct GitEntry {
    oid: String,
    blob: Vec<u8>,
    mode: String,
}

fn head_entry(cwd: &Path, path: &str) -> Result<Option<GitEntry>, String> {
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
    Ok(Some(GitEntry {
        oid,
        blob,
        mode: String::from_utf8_lossy(fields[0]).into_owned(),
    }))
}

fn index_entry(cwd: &Path, path: &str) -> Result<Option<GitEntry>, String> {
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
    Ok(Some(GitEntry {
        oid,
        blob,
        mode: String::from_utf8_lossy(fields[0]).into_owned(),
    }))
}

#[derive(Debug)]
struct PolicySnapshots {
    baseline: Policy,
    candidate: Policy,
    baseline_policy_oid: Option<String>,
    candidate_policy_oid: Option<String>,
    baseline_policy_mode: Option<String>,
    candidate_policy_mode: Option<String>,
}

fn policy_snapshots(cwd: &Path) -> Result<PolicySnapshots, String> {
    let baseline_entry = head_entry(cwd, ".statutor.yaml")?;
    let candidate_entry = index_entry(cwd, ".statutor.yaml")?;
    let baseline = match &baseline_entry {
        None => default_policy(),
        Some(entry) => std::str::from_utf8(&entry.blob)
            .map_err(|_| ())
            .and_then(parse_policy)
            .map_err(|_| {
                "HEAD:.statutor.yaml: invalid or unsupported Statutor policy".to_string()
            })?,
    };
    let candidate = match &candidate_entry {
        None => default_policy(),
        Some(entry) => std::str::from_utf8(&entry.blob)
            .map_err(|_| ())
            .and_then(parse_policy)
            .map_err(|_| ":.statutor.yaml: invalid or unsupported Statutor policy".to_string())?,
    };
    Ok(PolicySnapshots {
        baseline,
        candidate,
        baseline_policy_mode: baseline_entry.as_ref().map(|entry| entry.mode.clone()),
        candidate_policy_mode: candidate_entry.as_ref().map(|entry| entry.mode.clone()),
        baseline_policy_oid: baseline_entry.map(|entry| entry.oid),
        candidate_policy_oid: candidate_entry.map(|entry| entry.oid),
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
    if snapshots.baseline_policy_oid != snapshots.candidate_policy_oid
        || snapshots.baseline_policy_mode != snapshots.candidate_policy_mode
    {
        reserved.push(".statutor.yaml".to_string());
    }
    let baseline = head_entry(cwd, "CLAUDE.md")?;
    let candidate = index_entry(cwd, "CLAUDE.md")?;
    let baseline_exact = baseline
        .as_ref()
        .is_some_and(|entry| EXACT_CLAUDE_BRIDGES.contains(&entry.blob.as_slice()));
    let candidate_exact = candidate
        .as_ref()
        .is_some_and(|entry| EXACT_CLAUDE_BRIDGES.contains(&entry.blob.as_slice()));
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
    // Match Python dict.get: a missing key is None, not a parse failure.
    let Some(value) = map.get(&yaml_rust2::Yaml::from_str(key)) else {
        return Ok(None);
    };
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

fn state_tasks(content: &str, path: &str) -> Result<Vec<(String, String)>, String> {
    let mut tasks = Vec::new();
    let mut identities = HashSet::new();
    for (index, line) in python_lines(content).enumerate() {
        if !line.starts_with("- [") {
            continue;
        }
        let bytes = line.as_bytes();
        let valid_prefix = bytes.len() >= 7
            && matches!(bytes[3], b' ' | b'x' | b'X')
            && bytes[4] == b']'
            && bytes[5] == b' ';
        let parsed = valid_prefix.then(|| &line[6..]).and_then(|rest| {
            let split = rest.find(python_whitespace)?;
            let task_id = &rest[..split];
            let mut detail = rest[split..].chars();
            detail.next()?;
            detail.next()?;
            let digits = task_id.strip_prefix("T-")?;
            if digits.chars().count() < 4 || digits.starts_with(['+', '-']) {
                return None;
            }
            Some((task_id.to_string(), decimal_integer(digits)?))
        });
        let Some((task_id, number)) = parsed else {
            return Err(format!(
                "{path}: state line {} must be `- [ ] T-NNNN detail` or \
`- [x] T-NNNN detail`.",
                index + 1
            ));
        };
        if !identities.insert(task_id.clone()) {
            return Err(format!("{path}: duplicate state task ID {task_id}."));
        }
        tasks.push((task_id, number));
    }
    Ok(tasks)
}

fn state_reason(path: &str, candidate: &str, baseline: Option<&str>) -> Option<String> {
    let candidate_tasks = match state_tasks(candidate, path) {
        Ok(tasks) => tasks,
        Err(reason) => return Some(reason),
    };
    let Some(baseline) = baseline else {
        return None;
    };
    let baseline_tasks = match state_tasks(baseline, &format!("HEAD:{path}")) {
        Ok(tasks) => tasks,
        Err(reason) => return Some(reason),
    };
    let baseline_ids: HashSet<&str> = baseline_tasks.iter().map(|(id, _)| id.as_str()).collect();
    let candidate_ids: HashSet<&str> = candidate_tasks.iter().map(|(id, _)| id.as_str()).collect();
    let mut missing: Vec<String> = baseline_tasks
        .iter()
        .filter(|(task_id, _)| !candidate_ids.contains(task_id.as_str()))
        .map(|(task_id, _)| task_id.clone())
        .collect();
    missing.sort();
    if !missing.is_empty() {
        return Some(format!(
            "{path}: state task IDs cannot disappear or change: {}. \
Keep completed tasks in place.",
            py_list(&missing)
        ));
    }
    let number_cmp = |a: &str, b: &str| a.len().cmp(&b.len()).then_with(|| a.cmp(b));
    if let Some((_, maximum)) = baseline_tasks
        .iter()
        .max_by(|(_, a), (_, b)| number_cmp(a, b))
    {
        for (task_id, number) in &candidate_tasks {
            if !baseline_ids.contains(task_id.as_str())
                && number_cmp(number, maximum) != std::cmp::Ordering::Greater
            {
                let maximum = format!("{:0>4}", maximum);
                return Some(format!(
                    "{path}: new task ID {task_id} must be greater than existing \
maximum T-{maximum}."
                ));
            }
        }
    }
    None
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
        let old_rule = change.old.as_deref().and_then(|p| match_rule(p, policy, Some(cwd)));
        let new_rule = change.new.as_deref().and_then(|p| match_rule(p, policy, Some(cwd)));
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
        let Some(rule) = match_rule(path, policy, Some(cwd)) else {
            continue;
        };
        let code = change.status.as_bytes()[0] as char;
        match rule.policy.as_str() {
            "append_only" => {
                let old_rule = change.old.as_deref().and_then(|p| match_rule(p, policy, Some(cwd)));
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
            "state" => {
                let bytes = git(cwd, &["show", &format!(":{path}")])?;
                let candidate = match String::from_utf8(bytes) {
                    Ok(text) => text,
                    Err(_) => {
                        violations.push(format!("{path}: state content must be valid UTF-8 text."));
                        continue;
                    }
                };
                let old_rule = change.old.as_deref().and_then(|p| match_rule(p, policy, Some(cwd)));
                let same_rule = matches!(old_rule, Some(old) if std::ptr::eq(old, rule));
                let baseline = if matches!(code, 'M' | 'T') || (code == 'R' && same_rule) {
                    let old = change.old.as_deref().unwrap_or("");
                    let bytes = git(cwd, &["show", &format!("HEAD:{old}")])?;
                    match String::from_utf8(bytes) {
                        Ok(text) => Some(text),
                        Err(_) => {
                            violations.push(format!(
                                "HEAD:{old}: state content must be valid UTF-8 text."
                            ));
                            continue;
                        }
                    }
                } else {
                    None
                };
                if let Some(reason) = state_reason(path, &candidate, baseline.as_deref()) {
                    violations.push(reason);
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
        let raw_root = git(cwd, &["rev-parse", "--show-toplevel"])?;
        let root = PathBuf::from(
            String::from_utf8_lossy(raw_root.strip_suffix(b"\n").unwrap_or(&raw_root)).into_owned(),
        );
        let cwd = root.as_path();
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
        assert!(fnmatch("[^a]", "a"));
        assert!(fnmatch("[!a]", "["));
        assert!(fnmatch("*?", "*"));
        assert!(fnmatch("[b-a!]", "a"));
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
            match_rule("docs/DECISIONS.md", &p, None).unwrap().policy,
            "append_only"
        );
        assert_eq!(
            match_rule("plans/archive/x.md", &p, None).unwrap().policy,
            "frozen"
        );
        assert!(match_rule("src/main.rs", &p, None).is_none());
        assert_eq!(
            match_rule("plans\\archive\\win.md", &p, None).is_some(),
            cfg!(windows)
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

    #[test]
    fn state_ids_are_stable_while_details_and_order_may_change() {
        let baseline = "- [ ] T-0001 first\n- [ ] T-0002 second\n";
        let allowed = "- [x] T-0002 revised\n- [ ] T-0001 first revised\n- [ ] T-0003 new\n";
        assert_eq!(state_reason("TASKS.md", allowed, Some(baseline)), None);
        let removed = "- [ ] T-0001 first\n";
        assert!(state_reason("TASKS.md", removed, Some(baseline))
            .unwrap()
            .contains("T-0002"));
        let reused = "- [ ] T-0001 first\n- [ ] T-0002 second\n- [ ] T-0000 reused\n";
        assert!(state_reason("TASKS.md", reused, Some(baseline))
            .unwrap()
            .contains("greater than existing maximum"));
    }

    #[test]
    fn match_rule_case_variant_follows_directory_entry() {
        if let Ok(spec) = std::env::var("STATUTOR_MATCH_CASES") {
            let text = std::fs::read_to_string(&spec).expect("match cases");
            let mut lines = text.lines();
            let root = PathBuf::from(lines.next().expect("root"));
            let policy = default_policy();
            for rel in lines.filter(|line| !line.is_empty()) {
                let got = match_rule(rel, &policy, Some(&root))
                    .map(|rule| rule.policy.clone())
                    .unwrap_or_else(|| "none".to_string());
                println!("STATUTOR_MATCH {rel} {got}");
            }
            return;
        }

        let dir = std::env::temp_dir().join(format!("statutor-match-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).unwrap();
        std::fs::write(dir.join("AGENTS.md"), b"short\n").unwrap();
        let policy = default_policy();
        let variant = dir.join("agents.md");
        let canonical = dir.join("AGENTS.md");
        if super::same_file(&variant, &canonical) {
            assert_eq!(
                match_rule("agents.md", &policy, Some(&dir)).unwrap().policy,
                "constitution"
            );
        } else {
            assert!(match_rule("agents.md", &policy, Some(&dir)).is_none());
            std::fs::write(&variant, b"other\n").unwrap();
            assert!(match_rule("agents.md", &policy, Some(&dir)).is_none());
            assert_eq!(
                match_rule("AGENTS.md", &policy, Some(&dir)).unwrap().policy,
                "constitution"
            );
        }
        std::fs::create_dir_all(dir.join("notes")).unwrap();
        std::fs::write(dir.join("notes").join("agents.md"), b"nope\n").unwrap();
        assert!(match_rule("notes/agents.md", &policy, Some(&dir)).is_none());
        assert_eq!(
            match_rule("AGENTS.md", &policy, Some(&dir)).unwrap().policy,
            "constitution"
        );
        let _ = std::fs::remove_dir_all(&dir);
    }
}
