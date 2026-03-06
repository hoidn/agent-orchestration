use multiclass_metrics::{
    confusion_matrix, expected_calibration_error, macro_f1, per_class_metrics, top_k_accuracy,
};

#[test]
fn top_k_accuracy_handles_basic_case() {
    let probabilities = vec![
        vec![0.80, 0.10, 0.10],
        vec![0.20, 0.60, 0.20],
        vec![0.40, 0.40, 0.20],
    ];
    let targets = vec![0, 1, 1];

    let top1 = top_k_accuracy(&probabilities, &targets, 1).unwrap();
    let top2 = top_k_accuracy(&probabilities, &targets, 2).unwrap();

    assert!((top1 - (2.0 / 3.0)).abs() < 1e-12);
    assert!((top2 - 1.0).abs() < 1e-12);
}

#[test]
fn confusion_and_macro_f1_match_expected_values() {
    let probabilities = vec![
        vec![0.80, 0.10, 0.10],
        vec![0.20, 0.60, 0.20],
        vec![0.40, 0.40, 0.20],
        vec![0.10, 0.20, 0.70],
    ];
    let targets = vec![0, 1, 1, 2];

    let matrix = confusion_matrix(&probabilities, &targets, 3).unwrap();
    assert_eq!(matrix, vec![vec![1, 0, 0], vec![1, 1, 0], vec![0, 0, 1]]);

    let report = per_class_metrics(&matrix).unwrap();
    let macro_score = macro_f1(&report).unwrap();
    assert!((macro_score - (7.0 / 9.0)).abs() < 1e-12);
}

#[test]
fn expected_calibration_error_is_small_for_confident_correct_predictions() {
    let probabilities = vec![
        vec![0.90, 0.05, 0.05],
        vec![0.10, 0.80, 0.10],
        vec![0.05, 0.10, 0.85],
        vec![0.70, 0.20, 0.10],
    ];
    let targets = vec![0, 1, 2, 0];

    let ece = expected_calibration_error(&probabilities, &targets, 5).unwrap();
    assert!(ece >= 0.0);
    assert!(ece < 0.2);
}
