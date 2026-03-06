use sliding_window::{sliding_windows, window_start_indices, SlidingWindowError};

#[test]
fn sliding_windows_uses_stride_and_includes_short_tail_by_default() {
    let values = vec![1.0, 2.0, 3.0, 4.0, 5.0];

    let starts = window_start_indices(&values, 3, 2, false, None).unwrap();
    let windows = sliding_windows(&values, 3, 2, false, None).unwrap();

    assert_eq!(starts, vec![0, 2, 4]);
    assert_eq!(windows, vec![vec![1.0, 2.0, 3.0], vec![3.0, 4.0, 5.0], vec![5.0]]);
}

#[test]
fn sliding_windows_can_pad_or_drop_the_tail() {
    let values = vec![10.0, 20.0, 30.0, 40.0, 50.0];

    let padded = sliding_windows(&values, 4, 3, false, Some(0.0)).unwrap();
    let dropped = sliding_windows(&values, 4, 3, true, None).unwrap();

    assert_eq!(padded, vec![vec![10.0, 20.0, 30.0, 40.0], vec![40.0, 50.0, 0.0, 0.0]]);
    assert_eq!(dropped, vec![vec![10.0, 20.0, 30.0, 40.0]]);
}

#[test]
fn sliding_windows_reject_invalid_arguments() {
    let values = vec![1.0, 2.0, 3.0];

    assert_eq!(sliding_windows(&[], 2, 1, false, None), Err(SlidingWindowError::EmptyValues));
    assert_eq!(sliding_windows(&values, 0, 1, false, None), Err(SlidingWindowError::InvalidWindowSize));
    assert_eq!(sliding_windows(&values, 2, 0, false, None), Err(SlidingWindowError::InvalidStride));
    assert_eq!(sliding_windows(&values, 2, 1, true, Some(0.0)), Err(SlidingWindowError::ConflictingTailMode));
}
