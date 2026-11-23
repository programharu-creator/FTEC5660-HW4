"""Counterfactual tests for the assignment contracts. Author: eula."""
import os
import unittest
from unittest.mock import patch

os.environ['HW4_VARIANT'] = 'V6'
import hw4 as hw


def annual(company, year, cash, previous_cash):
    return f'''<html><head><title>{company} | Annual Report {year}</title></head><body>
    <h1>{company}</h1><p>Annual Report {year}</p><p>Headquarters: Wellington</p>
    <h2>Financial statements</h2><table><caption>Cash holdings (USD millions)</caption>
    <thead><tr><th>Item</th><th>{year}</th><th>{year-1}</th></tr></thead>
    <tbody><tr><th scope="row">Cash and cash equivalents</th><td>{cash}</td><td>{previous_cash}</td></tr></tbody></table>
    <h2>Governance</h2><p>A director joined in 2026.</p></body></html>'''


class RetrievalContracts(unittest.TestCase):
    def setUp(self):
        hw._HW4_COMPANIES.clear()
        hw._HW4_BROKERS.clear()
        self.guard = patch.object(hw, 'make_llm', side_effect=AssertionError('Unexpected model call'))
        self.guard.start()

    def tearDown(self):
        self.guard.stop()

    def build(self):
        documents = [annual('Westmere Analytics Inc.', 2031, '318.7', '280.1'),
                     annual('Westmere Payments Ltd.', 2031, '119.3', '103.4')]
        chunks = [c for i, text in enumerate(documents) for c in hw.chunk_document(f'arbitrary_{i}.html', text)]
        return chunks, hw.build_index(chunks)

    def test_multilevel_headers_and_printed_values(self):
        table = '''<table><caption>Measured amounts (USD millions)</caption><thead>
        <tr><th rowspan="2">Metric</th><th colspan="2">Annual values</th></tr>
        <tr><th>2031</th><th>2030</th></tr></thead><tbody>
        <tr><th scope="row">Net assets</th><td>1,712.3</td><td>(82.5)</td></tr></tbody></table>'''
        text = hw.table_to_text(table)
        self.assertIn('Measured amounts (USD millions)', text)
        self.assertTrue(any(all(v in line for v in ['Net assets', '2031', '1,712.3']) for line in text.splitlines()))
        self.assertTrue(any(all(v in line for v in ['Net assets', '2030', '(82.5)']) for line in text.splitlines()))

    def test_unknown_company_keeps_its_full_name(self):
        self.build()
        parsed = hw.parse_query('What was Westmere Analytics Systems revenue in FY2031?')
        self.assertEqual(parsed['companies'], ['Westmere Analytics Systems'])

    def test_possessive_company_does_not_absorb_role(self):
        self.build()
        parsed = hw.parse_query("Who was Westmere Analytics's Chief Financial Officer in FY2031?")
        self.assertEqual(parsed['companies'], ['Westmere Analytics'])
        self.assertEqual(parsed['doc_type'], 'annual_report')

    def test_operating_is_distinct_from_rating(self):
        self.build()
        self.assertEqual(hw.parse_query('What was Westmere Analytics operating income in FY2031?')['doc_type'], 'annual_report')

    def test_comparison_returns_original_chunks_for_both_companies(self):
        chunks, index = self.build()
        result = hw.retrieve(index, 'Which company held more cash in FY2031: Westmere Analytics or Westmere Payments?')
        self.assertLessEqual(len(result), 5)
        self.assertEqual({c.metadata['company'] for c in result}, {'Westmere Analytics Inc.', 'Westmere Payments Ltd.'})
        self.assertTrue(all(any(c is original for original in chunks) for c in result))

    def test_uncovered_year_ignores_incidental_old_director_date(self):
        _, index = self.build()
        self.assertEqual(hw.retrieve(index, 'How much cash did Westmere Analytics hold in FY2026?'), [])

    def test_unmentioned_subject_is_rejected_without_named_rule(self):
        _, index = self.build()
        self.assertEqual(hw.retrieve(index, 'What were Westmere Analytics political contributions in FY2031?'), [])

    def test_research_question_year_differs_from_document_year(self):
        html = '''<html><head><title>Research</title></head><body><div class="broker">Clearview Securities | Equity Research</div>
        <h1>Westmere Analytics Inc. (WMA)</h1><h2>FY2031 results review</h2>
        <table><caption>Revenue estimates</caption><thead><tr><th>Item</th><th>FY2032E</th></tr></thead>
        <tbody><tr><td>Revenue</td><td>965.8</td></tr></tbody></table></body></html>'''
        chunks = hw.chunk_document('unrelated_name.html', html)
        parsed = hw.parse_query('What FY2032 revenue does Clearview Securities forecast for Westmere Analytics?')
        self.assertEqual(parsed, {'companies': ['Westmere Analytics'], 'fiscal_year': 2032, 'doc_type': 'research_report'})
        result = hw.retrieve(hw.build_index(chunks), 'What FY2032 revenue does Clearview Securities forecast for Westmere Analytics?')
        self.assertTrue(result)
        self.assertTrue(all(c.metadata['fiscal_year'] == 2031 for c in result))

    def test_all_chunk_sizes_and_metadata(self):
        chunks, _ = self.build()
        self.assertTrue(all(len(c.page_content) <= 1500 for c in chunks))
        self.assertTrue(all(set(['source','company','fiscal_year','doc_type']) <= set(c.metadata) for c in chunks))
        self.assertEqual(hw.USAGE.llm_calls, 0)


if __name__ == '__main__':
    unittest.main()
