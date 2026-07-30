"""A tiny synthetic GST corpus so the whole pipeline runs offline in tests.

These passages are *written for this test suite*, loosely modelled on the shape
of real CGST Act sections and CBIC notifications. They are not legal text and
must never be used as one — the real corpus comes from `src/ingest/`.

The fixture exists to exercise structure, not content: section numbering,
supersession language, rate tables, acronyms, and the temporal questions that
make this domain interesting.
"""

from __future__ import annotations

from src.eval.goldset import GoldQuestion

DOCUMENTS: list[tuple[str, str, dict]] = [
    (
        "act-s16",
        """16. Eligibility and conditions for taking input tax credit.
        Every registered person shall, subject to such conditions and
        restrictions as may be prescribed, be entitled to take credit of input
        tax charged on any supply of goods or services which are used in the
        course or furtherance of his business. No registered person shall be
        entitled to the credit of any input tax in respect of any supply of
        goods or services unless he is in possession of a tax invoice, he has
        received the goods or services, the tax charged has been actually paid
        to the Government, and he has furnished the return under section 39.
        A registered person shall not be entitled to take input tax credit in
        respect of any invoice after the thirtieth day of November following the
        end of the financial year to which such invoice pertains.""",
        {"published": "2017-06-28", "doc_type": "act"},
    ),
    (
        "act-s17",
        """17. Apportionment of credit and blocked credits.
        Input tax credit shall not be available in respect of motor vehicles for
        transportation of persons having approved seating capacity of not more
        than thirteen persons, except when they are used for making a further
        supply of such motor vehicles or for transportation of passengers.
        Input tax credit shall not be available in respect of food and beverages,
        outdoor catering, health services, and leasing or renting of motor
        vehicles, except where an inward supply of such goods or services is
        used for making an outward taxable supply of the same category.""",
        {"published": "2017-06-28", "doc_type": "act"},
    ),
    (
        "act-s29",
        """29. Cancellation of registration.
        The proper officer may cancel the registration of a person where a
        registered person has not furnished returns for a continuous period of
        six months. Before cancelling any registration the proper officer shall
        issue a notice to such person requiring him to show cause within seven
        working days. The cancellation of registration shall not affect the
        liability of the person to pay tax and other dues for any period prior
        to the date of cancellation.""",
        {"published": "2017-06-28", "doc_type": "act"},
    ),
    (
        "act-s50",
        """50. Interest on delayed payment of tax.
        Every person who is liable to pay tax in accordance with the provisions
        of this Act but fails to pay the tax to the Government within the period
        prescribed shall for the period for which the tax remains unpaid pay
        interest at such rate not exceeding eighteen per cent as may be notified
        by the Government. Where a taxable person makes an undue or excess claim
        of input tax credit the rate of interest shall not exceed twenty-four
        per cent.""",
        {"published": "2017-06-28", "doc_type": "act"},
    ),
    (
        "notif-11-2017",
        """Notification No. 11/2017-CT(R). Rates of tax on supply of services.
        The Central Government hereby notifies that the central tax on the intra
        State supply of services shall be levied at the rates specified below.
        | Description of service | Rate |
        |---|---|
        | Accommodation in hotels where value of supply is less than 1000 | 0 |
        | Accommodation in hotels where value of supply is 1000 to 7500 | 12 |
        | Accommodation in hotels where value of supply exceeds 7500 | 18 |
        | Restaurant service other than at specified premises | 5 |
        This notification shall come into force on the 1st day of July 2017.""",
        {"published": "2017-06-28", "doc_type": "notification",
         "notification_id": "11/2017-CT(R)"},
    ),
    (
        "notif-20-2019",
        """Notification No. 20/2019-CT(R). Seeks to amend Notification No.
        11/2017-CT(R) so as to revise the rates applicable to accommodation
        services. In the said notification, for the entry relating to
        accommodation in hotels where the value of supply exceeds 7500 rupees,
        the rate of twelve per cent shall be substituted with effect from the
        1st day of October 2019. Accommodation where the value of supply is up
        to 1000 rupees per unit per day shall be exempt.""",
        {"published": "2019-09-30", "doc_type": "notification",
         "notification_id": "20/2019-CT(R)"},
    ),
    (
        "circ-183-2022",
        """Circular No. 183/15/2022-GST. Clarification on the manner of dealing
        with difference in input tax credit availed in FORM GSTR-3B as compared
        to that detailed in FORM GSTR-2A. Where the difference between the input
        tax credit claimed by the registered person and that available in FORM
        GSTR-2A exceeds five lakh rupees, the proper officer shall ask the
        registered person to produce a certificate from a chartered accountant
        certifying that the supplies have actually been made by the supplier and
        the tax on such supplies has been paid.""",
        {"published": "2022-12-27", "doc_type": "circular"},
    ),
    (
        "circ-125-2019",
        """Circular No. 125/44/2019-GST. Fully electronic refund process through
        FORM GST RFD-01. In supersession of Notification No. 11/2017-CT(R) to
        the extent it relates to refund procedure, the Board clarifies that all
        refund applications shall be filed electronically. A refund application
        for unutilised input tax credit on account of zero rated supplies may be
        filed for a period not exceeding two years from the relevant date. The
        acknowledgement in FORM GST RFD-02 shall be issued within fifteen days.""",
        {"published": "2019-11-18", "doc_type": "circular"},
    ),
    (
        "act-s47",
        """47. Levy of late fee.
        Any registered person who fails to furnish the details of outward
        supplies required under section 37 or returns required under section 39
        by the due date shall pay a late fee of one hundred rupees for every day
        during which such failure continues subject to a maximum amount of five
        thousand rupees.""",
        {"published": "2017-06-28", "doc_type": "act"},
    ),
    (
        "act-s22",
        """22. Persons liable for registration.
        Every supplier shall be liable to be registered under this Act in the
        State from where he makes a taxable supply of goods or services if his
        aggregate turnover in a financial year exceeds twenty lakh rupees. Where
        such person makes taxable supplies from any of the special category
        States he shall be liable to be registered if his aggregate turnover
        exceeds ten lakh rupees.""",
        {"published": "2017-06-28", "doc_type": "act"},
    ),
]


def gold_questions() -> list[GoldQuestion]:
    """A miniature gold set. Chunk ids assume the 'section' chunking strategy.

    Note the mix: acronym-heavy queries that only work with rewriting, a temporal
    question where the superseded notification is the wrong answer, and an
    unanswerable question to check abstention.
    """
    return [
        GoldQuestion(
            question_id="q1",
            question="Can I claim ITC on a hotel stay for a business trip?",
            relevant_chunk_ids=["act-s17::sec17::0"],
            source="forum",
            question_type="conditional",
            split="test",
            reference_answer="No. Input tax credit is blocked on food and beverages "
            "and on leasing or renting of motor vehicles, and accommodation-related "
            "inward supplies are restricted under section 17.",
        ),
        GoldQuestion(
            question_id="q2",
            question="What is the time limit for taking input tax credit on an invoice?",
            relevant_chunk_ids=["act-s16::sec16::0"],
            source="faq",
            question_type="factual",
            split="test",
            reference_answer="30 November following the end of the financial year to "
            "which the invoice pertains.",
        ),
        GoldQuestion(
            question_id="q3",
            question="What interest is payable on delayed payment of GST?",
            relevant_chunk_ids=["act-s50::sec50::0"],
            source="exam",
            question_type="factual",
            split="test",
            reference_answer="Up to 18 per cent, and up to 24 per cent for undue or "
            "excess input tax credit claims.",
        ),
        GoldQuestion(
            question_id="q4",
            question="When can the proper officer cancel a GST registration?",
            relevant_chunk_ids=["act-s29::sec29::0"],
            source="practitioner",
            question_type="procedural",
            split="test",
        ),
        GoldQuestion(
            question_id="q5",
            question="What is the late fee for not filing a return on time?",
            relevant_chunk_ids=["act-s47::sec47::0"],
            source="faq",
            question_type="factual",
            split="test",
            reference_answer="100 rupees per day subject to a maximum of 5000 rupees.",
        ),
        GoldQuestion(
            question_id="q6",
            question="What is the turnover threshold for GST registration?",
            relevant_chunk_ids=["act-s22::sec22::0"],
            source="faq",
            question_type="factual",
            split="test",
            reference_answer="20 lakh rupees, or 10 lakh rupees for special category States.",
        ),
        GoldQuestion(
            question_id="q7",
            question="What certificate is needed when the GSTR-2A mismatch exceeds 5 lakh?",
            relevant_chunk_ids=["circ-183-2022::fixed::0"],
            source="practitioner",
            question_type="conditional",
            split="test",
            reference_answer="A chartered accountant's certificate.",
        ),
        GoldQuestion(
            question_id="q8",
            question="How long do I have to file a refund claim for unutilised ITC?",
            relevant_chunk_ids=["circ-125-2019::fixed::0"],
            source="forum",
            question_type="procedural",
            split="test",
            reference_answer="Two years from the relevant date.",
        ),
        GoldQuestion(
            question_id="q9",
            question="What is the GST rate on hotel accommodation above 7500 rupees?",
            relevant_chunk_ids=["notif-20-2019::fixed::0", "notif-11-2017::fixed::0"],
            graded_relevance={"notif-20-2019::fixed::0": 3.0, "notif-11-2017::fixed::0": 1.0},
            source="forum",
            question_type="temporal",
            split="test",
            as_of="2024-04-01",
            reference_answer="12 per cent, following the amendment by Notification "
            "20/2019-CT(R) with effect from 1 October 2019.",
            notes="The 2017 notification says 18%. Retrieving it first is a "
            "correctness failure, not just a ranking failure.",
        ),
        GoldQuestion(
            question_id="q10",
            question="What is the GST rate on cryptocurrency mining rigs?",
            relevant_chunk_ids=[],
            source="practitioner",
            question_type="unanswerable",
            split="test",
            notes="Not covered by the fixture corpus; the system must abstain.",
        ),
    ]
