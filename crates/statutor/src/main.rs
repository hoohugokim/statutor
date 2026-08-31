//! `statutor-staged [DIR]` — native local git-floor binary.
//!
//! Byte-compatible twin of `statutor staged` (see lib.rs and DECISIONS.md
//! D-0014). Intended for local pre-commit and CI checks of a working tree's
//! staged index; interactive surfaces stay with the Python CLI.

use std::process::exit;

fn main() {
    let cwd = std::env::args()
        .nth(1)
        .map(std::path::PathBuf::from)
        .unwrap_or_else(|| std::env::current_dir().expect("cwd"));
    let (code, stdout) = statutor::run_staged(&cwd);
    if !stdout.is_empty() {
        print!("{stdout}");
    }
    exit(code);
}
