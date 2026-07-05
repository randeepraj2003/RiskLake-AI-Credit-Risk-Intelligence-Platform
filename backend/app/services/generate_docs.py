"""
RiskLake — Mock Lending Guidelines Generator
=============================================
Generates realistic lending policy documents that the RAG pipeline
ingests into ChromaDB. In production, replace these with:
  - RBI Master Circular on Loans and Advances
  - Basel III Credit Risk Guidelines
  - ANZ Internal Credit Policy (PDFs)
  - FATF AML Typologies

Run once before ingest_docs.py:
    python rag/generate_docs.py

Output: rag/docs/*.txt
"""

from pathlib import Path

DOCS_DIR = Path(__file__).parent / "docs"
DOCS_DIR.mkdir(exist_ok=True)

docs = {

"rbi_credit_policy.txt": """
RBI MASTER CIRCULAR — CREDIT RISK MANAGEMENT
Source: Reserve Bank of India, Prudential Norms on Income Recognition

SECTION 1: CLASSIFICATION OF LOAN ASSETS
==========================================
Banks shall classify their loan assets into the following categories:
- Standard Assets: Accounts which do not disclose any problems.
- Sub-Standard Assets: Accounts which have remained NPA for less than 12 months.
- Doubtful Assets: Accounts which have remained in the sub-standard category for 12 months.
- Loss Assets: Accounts where loss has been identified by the bank or internal/external auditors.

SECTION 2: INCOME RECOGNITION
==============================
Banks should not recognise interest income on a cash basis in respect of:
- Non-Performing Assets (NPAs)
- Any advances where interest has not been received for more than 90 days

SECTION 3: PROVISIONING NORMS
==============================
Standard Assets: General provision of 0.25% to 1% based on category.
Sub-standard Assets: 15% of the outstanding loan balance.
Doubtful Assets (up to 1 year): 25% of outstanding balance.
Doubtful Assets (1-3 years): 40% of outstanding balance.
Doubtful Assets (more than 3 years): 100% of outstanding balance.
Loss Assets: 100% provision required immediately.

SECTION 4: DEBT-TO-INCOME RATIO THRESHOLDS
============================================
Banks are advised to adhere to the following DTI norms for retail lending:
- DTI below 0.36 (36%): Low risk. Loans may be approved under standard terms.
- DTI between 0.36 and 0.43 (36-43%): Moderate risk. Enhanced scrutiny required.
- DTI between 0.43 and 0.50 (43-50%): Elevated risk. Senior credit officer approval needed.
- DTI above 0.50 (50%): High risk. Applications should generally be declined unless
  strong mitigating factors exist such as high collateral value or guarantor support.

SECTION 5: CREDIT SCORE REQUIREMENTS
======================================
For retail and personal loans, the following minimum credit score thresholds apply:
- Home loans: Minimum CIBIL score of 700 recommended.
- Personal loans (unsecured): Minimum CIBIL score of 650 recommended.
- Auto loans: Minimum CIBIL score of 620 recommended.
- Credit cards: Minimum CIBIL score of 650 recommended.
Applicants with credit scores below 550 are classified as high-risk and
require additional collateral or guarantor support.

SECTION 6: COLLATERAL REQUIREMENTS
=====================================
Secured lending requires collateral coverage ratio (CCR) of:
- Home loans: CCR >= 1.20 (collateral value at least 120% of loan amount)
- Business loans: CCR >= 1.50
- Personal loans: Unsecured; no CCR requirement but stricter income verification
Collateral must be independently valued by RBI-approved valuers.
""",

"basel_iii_credit_risk.txt": """
BASEL III FRAMEWORK — CREDIT RISK CAPITAL REQUIREMENTS
Source: Bank for International Settlements, Basel Committee on Banking Supervision

SECTION 1: PROBABILITY OF DEFAULT (PD)
========================================
The Probability of Default (PD) represents the likelihood that a borrower
will default within a one-year horizon. Under the Internal Ratings-Based (IRB)
approach, banks must estimate PD for each exposure:

PD Risk Grade Classification:
- Grade A (PD < 5%):  Minimal risk. Standard pricing applies.
- Grade B (PD 5-15%): Low-moderate risk. Risk-adjusted pricing required.
- Grade C (PD 15-30%): Moderate risk. Enhanced monitoring and higher provisions.
- Grade D (PD 30-50%): High risk. Loan loss provisions at 40-60%.
- Grade E (PD > 50%): Very high risk. Full provision recommended; consider declining.

SECTION 2: LOSS GIVEN DEFAULT (LGD)
======================================
LGD is the fraction of the exposure that will be lost if the borrower defaults.
- Secured loans (real estate): LGD typically 20-40%
- Secured loans (other collateral): LGD typically 40-60%
- Unsecured loans: LGD typically 60-85%

SECTION 3: RISK-WEIGHTED ASSETS (RWA)
=======================================
Credit RWA = Exposure at Default (EAD) × Risk Weight
Risk weights under the standardised approach:
- Claims rated AAA to AA-: 20% risk weight
- Claims rated A+ to A-: 50% risk weight
- Claims rated BBB+ to BB-: 100% risk weight
- Claims rated below BB-: 150% risk weight
- Unrated claims: 100% risk weight

SECTION 4: KEY RISK INDICATORS FOR EARLY WARNING
==================================================
Banks should monitor the following early warning indicators (EWIs):
1. Credit utilisation increase of more than 20% in 90 days
2. Three or more hard credit inquiries within 6 months
3. Delinquency rate exceeding 10% of total accounts
4. EMI payment regularity score below 0.5 (payments made in fewer than half of months)
5. Debt-to-income ratio increase of more than 10 percentage points in 12 months
6. Negative balance trend: average balance declining for 3+ consecutive months
7. Flagged transaction rate exceeding 5% of total monthly transactions

SECTION 5: CREDIT STRESS SCORING
===================================
A composite credit stress score is recommended for rapid risk assessment.
Score components (each contributes 1 point to a 0-4 scale):
- High inquiry flag (>=3 hard pulls in 6 months): +1
- Balance trend flag (balance growing month-over-month): +1
- Low EMI regularity (<50% of months with payment): +1
- High flagged transaction rate (>5%): +1

Stress score interpretation:
- Score 0: No stress indicators. Standard approval process.
- Score 1: Minor stress. Proceed with standard enhanced due diligence.
- Score 2: Moderate stress. Senior credit officer review required.
- Score 3: High stress. Decline recommended unless exceptional circumstances.
- Score 4: Severe stress. Automatic decline.
""",

"aml_typologies.txt": """
FATF — AML/CFT RISK TYPOLOGIES FOR RETAIL BANKING
Source: Financial Action Task Force, Guidance for Retail Banking Sector

SECTION 1: TRANSACTION MONITORING RED FLAGS
============================================
The following transaction patterns should trigger enhanced due diligence (EDD):

High-Risk Transaction Indicators:
1. Large cash deposits or withdrawals inconsistent with customer profile
2. Rapid movement of funds through multiple accounts (layering)
3. Transactions involving high-risk jurisdictions
4. Multiple small transactions just below reporting thresholds (structuring)
5. Transactions inconsistent with stated business or income source
6. Sudden increase in transaction frequency or volume without explanation

Customer Risk Indicators:
1. Politically Exposed Persons (PEPs) or close associates
2. Customers operating in high-risk industries (cash-intensive businesses)
3. Customers with unexplained wealth or income inconsistent with lifestyle
4. Multiple address changes or inconsistent personal information

SECTION 2: SUSPICIOUS ACTIVITY REPORTING (SAR)
================================================
A Suspicious Activity Report (SAR) must be filed when:
- A transaction of INR 10 lakh or more in cash is conducted
- Multiple transactions totalling INR 10 lakh or more are conducted in a month
- Any transaction appears to be structured to avoid reporting thresholds
- Transactions involve suspected proceeds of crime

SECTION 3: CREDIT RISK AND MONEY LAUNDERING NEXUS
===================================================
Loan facilities can be misused for money laundering:
1. Loan-Back Schemes: Criminal deposits funds as collateral, takes loan against it,
   defaults, and the institution retains the 'clean' collateral.
2. Trade Finance Abuse: Over/under-invoicing of goods to move value across borders.
3. Mortgage Fraud: Property purchased with illicit funds through complex ownership.

Risk mitigation:
- Enhanced CDD for loan amounts above INR 50 lakh
- Verify income source documentation for DTI calculation
- Cross-reference collateral ownership with beneficial ownership registry
""",

"loan_product_guidelines.txt": """
RISKLAKE INTERNAL — LOAN PRODUCT CREDIT GUIDELINES
Version: 2024.1

PRODUCT 1: HOME LOANS
======================
Maximum loan amount: INR 5 crore
Maximum LTV ratio: 80% (90% for loans up to INR 30 lakh)
Maximum loan tenure: 30 years
Minimum credit score: 700 (CIBIL)
Minimum income: INR 3 lakh per annum (salaried); INR 5 lakh (self-employed)
Maximum DTI (including new EMI): 45%
Employment stability: Minimum 2 years in current employment
Collateral: Property being purchased; CCR >= 1.20

PRODUCT 2: PERSONAL LOANS (UNSECURED)
=======================================
Maximum loan amount: INR 25 lakh
Maximum loan tenure: 5 years
Minimum credit score: 650 (CIBIL)
Minimum income: INR 2.5 lakh per annum
Maximum DTI (including new EMI): 40%
Employment stability: Minimum 1 year in current employment
No collateral required; income and credit score are primary underwriting factors.

PRODUCT 3: AUTO LOANS
======================
Maximum loan amount: INR 50 lakh
Maximum LTV ratio: 85% of on-road vehicle price
Maximum loan tenure: 7 years
Minimum credit score: 620 (CIBIL)
Maximum DTI: 42%
Collateral: Vehicle being purchased; hypothecated to bank until loan closure.

PRODUCT 4: BUSINESS LOANS (SME)
=================================
Maximum loan amount: INR 2 crore
Maximum loan tenure: 10 years
Minimum credit score (proprietor): 650 (CIBIL)
Business vintage: Minimum 2 years of operations
Maximum DTI: 50% (business cash flow considered separately)
Collateral: CCR >= 1.50; primary + collateral security required

APPROVAL AUTHORITY MATRIX
===========================
Loan Amount         | Approving Authority
INR 0 - 25 lakh     | Branch Credit Manager
INR 25 - 75 lakh    | Regional Credit Head
INR 75 lakh - 2 cr  | Zonal Credit Committee
Above INR 2 crore   | Central Credit Committee

OVERRIDE POLICY
================
Standard declining criteria may be overridden under the following conditions:
1. Customer relationship value > INR 1 crore total deposits
2. Additional collateral coverage brings CCR above 2.0
3. Guarantor with net worth > 3x loan amount and CIBIL score > 750
4. Written approval from two senior credit officers required for any override
"""
}

for filename, content in docs.items():
    path = DOCS_DIR / filename
    path.write_text(content.strip())
    print(f"Written: {path}")

print(f"\n{len(docs)} policy documents written to {DOCS_DIR}")
