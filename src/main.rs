//! CLI entry point for corpora-core.
//!
//! Build with `cargo build --features cli`.

use clap::Parser;

/// CLI for corpora-core operations.
#[derive(Parser, Debug)]
#[command(name = "corpora-core")]
#[command(author, version, about, long_about = None)]
struct Args {
    /// First number to add
    #[arg(short, long)]
    left: u64,

    /// Second number to add
    #[arg(short, long)]
    right: u64,
}

fn main() {
    let args = Args::parse();
    let result = corpora_core::add(args.left, args.right);
    println!("{result}");
}
