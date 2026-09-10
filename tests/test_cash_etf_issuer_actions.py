from __future__ import annotations

from trading_platform.cash_etf_issuer_actions import (
    document_index_proves_zero_splits,
    extract_dbc_distribution_table,
    extract_dbc_event_detail,
    extract_explicit_zero_distribution_years,
    gld_proves_zero_distributions,
)
from trading_platform.cash_etf_issuer_actions_v2 import (
    extract_explicit_zero_distribution_years as extract_explicit_zero_distribution_years_v2,
)


def test_extracts_dbc_three_year_distribution_table() -> None:
    text = (
        "Years Ended December 31, 2023 2022 2021 "
        "Distributions per General Share $ 1.08926 $ 0.14467 $ — "
        "Distributions per Share $ 1.08926 $ 0.14467 $ —"
    )
    assert extract_dbc_distribution_table(text) == {
        2021: "0",
        2022: "0.14467",
        2023: "1.08926",
    }


def test_extracts_explicit_combined_zero_distribution_years() -> None:
    text = "No distributions were paid for the Years Ended December 31, 2014, 2013 and 2012."
    assert extract_explicit_zero_distribution_years(text) == {2012, 2013, 2014}


def test_v2_extracts_lowercase_singular_issuer_wording() -> None:
    text = "No distributions were paid to Shareholders during the year ended December 31, 2015."
    assert extract_explicit_zero_distribution_years_v2(text) == {2015}


def test_extracts_dbc_event_detail() -> None:
    text = (
        "A distribution for the year ended December 31, 2018 was paid on December 31, 2018 "
        "to holders of record as of December 26, 2018 at a rate of $0.18853 for each Share."
    )
    assert extract_dbc_event_detail(text) == {
        "amount_per_share": "0.18853",
        "payable_date": "2018-12-31",
        "record_date": "2018-12-26",
        "year": "2018",
    }


def test_document_index_absence_does_not_prove_zero_splits() -> None:
    assert not document_index_proves_zero_splits(
        "Fund documents, annual reports, prospectus", "2009-01-02", "2023-12-31"
    )


def test_document_index_requires_explicit_scope_and_zero_statement() -> None:
    text = (
        "Complete corporate action history from 2009-01-02 through 2023-12-31: "
        "no stock splits or reverse stock splits."
    )
    assert document_index_proves_zero_splits(text, "2009-01-02", "2023-12-31")


def test_gld_no_income_statement_is_not_a_zero_distribution_history() -> None:
    assert not gld_proves_zero_distributions(
        ["The Trust does not generate any income."], "2009-01-02", "2023-12-31"
    )
