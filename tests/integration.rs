//! Integration tests for corpora-core.

use corpora_core::add;

#[test]
fn add_should_work_with_large_numbers() {
    let result = add(u64::MAX / 2, u64::MAX / 2);
    assert_eq!(result, u64::MAX - 1);
}
