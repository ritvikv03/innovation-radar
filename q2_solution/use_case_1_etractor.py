"""
Use Case 1: Electric Tractor Subsidy & Business Intelligence
============================================================

Generates structured intelligence on:
- EU / country-specific subsidy and incentive programs for electric tractors
- Business impact assessment for AGCO/Fendt
- Sales recommendations (competitor activity, revenue planning, market establishment)
- Marketing recommendations (strategy, campaigns, communication)
- E-tractor specific customer needs vs. standard diesel tractor

No AI API calls — fully rule-based + signal-database-driven.
"""

from typing import List, Dict, Optional


# ============================================================
# STATIC KNOWLEDGE BASE: Subsidy & Incentive Programs
# ============================================================

SUBSIDY_KNOWLEDGE_BASE: Dict[str, Dict] = {
    'EU / EME': {
        'headline': 'EU-wide frameworks create the subsidy floor for all member states.',
        'programs': [
            {
                'name': 'CAP Eco-Schemes 2023–2027',
                'description': (
                    'Common Agricultural Policy direct payments include mandatory eco-schemes '
                    'where at least 25% of funds must incentivize sustainable practices. '
                    'Member states are increasingly allowing electric/zero-emission machinery '
                    'investment as an eligible eco-scheme activity.'
                ),
                'amount': '€387 billion total (2021–2027); eco-scheme share varies per member state',
                'timeline': '2023–2027',
                'relevance': 'HIGH',
                'type': 'Grant / Direct Payment',
                'url': 'https://agriculture.ec.europa.eu/common-agricultural-policy/cap-overview/cap-2023-27_en',
            },
            {
                'name': 'EU Battery Regulation (2023/1542)',
                'description': (
                    'Mandates lifecycle tracking, carbon footprint declarations, and recycled content '
                    'requirements for agricultural tractor batteries from 2027. '
                    'Creates compliance cost pressure that simultaneously drives demand for '
                    'EU-compliant electric tractor platforms.'
                ),
                'amount': 'Compliance cost (not direct subsidy) — creates market pull',
                'timeline': '2024–2027 phased',
                'relevance': 'CRITICAL',
                'type': 'Regulatory Mandate',
                'url': 'https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A32023R1542',
            },
            {
                'name': 'EAFRD — Rural Development Fund',
                'description': (
                    'European Agricultural Fund for Rural Development funds farm modernization '
                    'including precision agriculture, digitalization, and low-emission machinery '
                    'adoption. Charging infrastructure for electric tractors is an emerging '
                    'eligible investment category.'
                ),
                'amount': '€95 billion (2021–2027) across member states',
                'timeline': '2021–2027',
                'relevance': 'MODERATE',
                'type': 'Investment Grant (via member states)',
                'url': 'https://agriculture.ec.europa.eu/common-agricultural-policy/rural-development_en',
            },
            {
                'name': 'Horizon Europe — Agriculture & Food Cluster',
                'description': (
                    'R&D and innovation funding for agricultural electrification technology, '
                    'battery chemistry, autonomous systems, and precision farming. '
                    'Fendt/AGCO is eligible as a manufacturer participating in research consortia.'
                ),
                'amount': '€95.5 billion total; agriculture cluster within',
                'timeline': '2021–2027',
                'relevance': 'MODERATE',
                'type': 'R&D Grant',
                'url': 'https://research-and-innovation.ec.europa.eu/funding/funding-opportunities/funding-programmes-and-open-calls/horizon-europe_en',
            },
        ],
    },
    'Germany': {
        'headline': 'Germany combines federal efficiency grants, KfW low-interest loans, and Länder-level AFP co-financing.',
        'programs': [
            {
                'name': 'Agrarinvestitionsförderungsprogramm (AFP)',
                'description': (
                    'Federal/Länder co-financed investment grant for agricultural modernization. '
                    'Electric tractor procurement explicitly qualifies as a sustainable investment '
                    'under current AFP guidelines in Bavaria, Baden-Württemberg, and Lower Saxony. '
                    'Most competitive subsidy for direct tractor purchase.'
                ),
                'amount': '20–40% investment grant (varies by Bundesland and project type)',
                'timeline': 'Ongoing, CAP-aligned cycles',
                'relevance': 'HIGH',
                'type': 'Investment Grant',
                'url': 'https://www.bmel.de/DE/themen/landwirtschaft/foerderung/agrarinvestitionsprogramm.html',
            },
            {
                'name': 'BAFA — Bundesförderung Energie und Ressourceneffizienz in der Wirtschaft',
                'description': (
                    'Federal efficiency grants for energy-efficient industrial and agricultural '
                    'machinery. Electric tractors qualify under Module 1 (cross-sector energy '
                    'efficiency) when demonstrated energy savings vs. diesel baseline are documented.'
                ),
                'amount': 'Up to 50% of eligible investment costs',
                'timeline': 'Ongoing',
                'relevance': 'HIGH',
                'type': 'Investment Grant',
                'url': 'https://www.bafa.de/DE/Energie/Energieeffizienz/',
            },
            {
                'name': 'KfW Erneuerbare Energien — Speicher (270)',
                'description': (
                    'Low-interest loan for energy storage systems. Agricultural battery '
                    'storage for tractor charging infrastructure qualifies. '
                    'Combined with AFP grants, effectively reduces net equipment cost significantly.'
                ),
                'amount': 'Low-interest loans up to €10 million at 1–3% p.a.',
                'timeline': 'Ongoing',
                'relevance': 'MODERATE',
                'type': 'Low-Interest Loan',
                'url': 'https://www.kfw.de/inlandsfoerderung/Unternehmen/Energie-Umwelt/F%C3%B6rderprodukte/Erneuerbare-Energien-%E2%80%93-Speicher-(270)/',
            },
        ],
    },
    'France': {
        'headline': 'France 2030 is the most aggressive national agricultural electrification program in Western Europe.',
        'programs': [
            {
                'name': 'Plan France 2030 — Agriculture Decarbonization',
                'description': (
                    'National investment plan with dedicated €1.7B envelope for agricultural '
                    'decarbonization. Specifically funds electric and hydrogen-powered agricultural '
                    'machinery R&D, fleet adoption, and dealer network capability building. '
                    'Managed by BpiFrance — direct grant applications open to OEMs and dealers.'
                ),
                'amount': '€1.7 billion for agriculture sector; per-project up to €5 million',
                'timeline': '2022–2030',
                'relevance': 'HIGH',
                'type': 'Investment Grant + R&D Funding',
                'url': 'https://www.gouvernement.fr/france-2030',
            },
            {
                'name': 'ADEME — Décarbonation de l\'Agriculture',
                'description': (
                    'French Environment and Energy Management Agency grants for low-emission '
                    'agricultural equipment including electric tractors and charging infrastructure. '
                    'ADEME also funds farmer education programs on electric equipment operation.'
                ),
                'amount': 'Variable, typically 30–40% of eligible costs',
                'timeline': 'Ongoing rolling calls',
                'relevance': 'HIGH',
                'type': 'Investment Grant',
                'url': 'https://www.ademe.fr',
            },
            {
                'name': 'PCAE — Plan de Compétitivité et d\'Adaptation des Exploitations',
                'description': (
                    'Regional farm competitiveness grants co-financed by EU EAFRD and French regions. '
                    'Electric equipment adoption is an explicitly supported category under '
                    'sustainability investment criteria. Application via regional agricultural chambers.'
                ),
                'amount': '30–40% grant; ceiling varies by region (typically €150,000–€500,000)',
                'timeline': '2023–2027 (CAP-aligned)',
                'relevance': 'HIGH',
                'type': 'Regional Investment Grant',
                'url': 'https://agriculture.gouv.fr/le-plan-de-competitivite-et-dadaptation-des-exploitations-agricoles-pcae',
            },
        ],
    },
    'UK': {
        'headline': 'Post-Brexit UK has replaced CAP with direct domestic programs; Farming Investment Fund is the most accessible route.',
        'programs': [
            {
                'name': 'Farming Investment Fund (FIF) — FETF',
                'description': (
                    'UK Government\'s Farming Equipment and Technology Fund grants for '
                    'agricultural equipment including electric vehicles, precision agriculture, '
                    'and automation. Electric tractors and EV charging stations for farms '
                    'are eligible categories. Open applications, no competitive bidding.'
                ),
                'amount': '£25,000–£500,000 per application (capital items); fixed grant rates per item',
                'timeline': 'Ongoing (rolling windows)',
                'relevance': 'HIGH',
                'type': 'Capital Grant',
                'url': 'https://www.gov.uk/guidance/farming-investment-fund',
            },
            {
                'name': 'Sustainable Farming Incentive (SFI)',
                'description': (
                    'Annual payment scheme for sustainable farming practices. '
                    'While not a direct machinery grant, SFI income improves farm financial '
                    'health, enabling investment in premium electric equipment. '
                    'Anticipated to include low-emission machinery actions from 2025.'
                ),
                'amount': 'Up to £98/ha/year (varies by action)',
                'timeline': '2023–ongoing',
                'relevance': 'MODERATE',
                'type': 'Annual Payment',
                'url': 'https://www.gov.uk/guidance/sustainable-farming-incentive-how-the-scheme-works',
            },
            {
                'name': 'UK Net Zero Agriculture Strategy (Anticipated)',
                'description': (
                    'Defra is developing targeted grants for low-emission agricultural machinery '
                    'aligned with the UK\'s 2040 agricultural net-zero commitment. '
                    'Electric tractor specific grants anticipated in 2025–2026 Spending Review.'
                ),
                'amount': 'TBD — policy under consultation',
                'timeline': '2025–2030 (anticipated)',
                'relevance': 'MODERATE',
                'type': 'Anticipated Grant Program',
                'url': 'https://www.gov.uk/government/publications/agricultural-transition-plan',
            },
        ],
    },
    'Norway': {
        'headline': 'Norway is the most EV-advanced market globally — agricultural electrification programs are the most mature.',
        'programs': [
            {
                'name': 'Enova — Landbruk (Agriculture Energy Transition)',
                'description': (
                    'Norwegian energy agency grants specifically for low/zero-emission '
                    'technology in agriculture. Electric tractor charging infrastructure '
                    'and pilot fleet purchases are eligible. Norway leads globally in '
                    'agricultural EV pilot deployments.'
                ),
                'amount': 'Up to NOK 1.5 million per farm project (~€130,000)',
                'timeline': 'Ongoing',
                'relevance': 'HIGH',
                'type': 'Capital Grant',
                'url': 'https://www.enova.no/bedrift/landbruk/',
            },
            {
                'name': 'Innovasjon Norge — Agricultural Technology',
                'description': (
                    'Norwegian Innovation Agency investment grants for agricultural technology '
                    'adoption including electric machinery. Most accessible for farm '
                    'operations and agricultural cooperatives.'
                ),
                'amount': 'Up to 45% of project cost',
                'timeline': 'Ongoing rolling calls',
                'relevance': 'HIGH',
                'type': 'Investment Grant',
                'url': 'https://www.innovasjonnorge.no/en/start-page/',
            },
            {
                'name': 'Jordbruksavtalen — Annual Agricultural Agreement',
                'description': (
                    'Annual negotiated agricultural support framework between Norwegian '
                    'government and farmer organizations. Since 2023, climate technology '
                    'adoption — including electric tractors — is a funded priority action. '
                    'Provides operational subsidy support beyond capital grants.'
                ),
                'amount': 'Variable within annual NOK 17+ billion framework',
                'timeline': 'Annual renewal',
                'relevance': 'HIGH',
                'type': 'Operational Support + Capital',
                'url': 'https://www.regjeringen.no/en/topics/food-fisheries-and-agriculture/agriculture/jordbruksavtalen/',
            },
        ],
    },
}

# ============================================================
# SEARCH KEYWORDS
# ============================================================

ETRACTOR_SIGNAL_KEYWORDS = [
    'electric tractor', 'e-tractor', 'battery tractor', 'electrification',
    'zero emission tractor', 'ev agriculture', 'battery swap', 'charging infrastructure',
    'agricultural ev', 'electric farm', 'tractor battery', 'autonomous tractor',
    'farm electrification', 'cap subsidy', 'green deal', 'farm to fork',
    'bafa', 'kfw agriculture', 'battery regulation', 'eu battery mandate',
    'agricultural subsidy', 'precision farming', 'hydrogen tractor',
    'electric machinery', 'battery technology', 'charging station',
]

COMPETITOR_SIGNAL_KEYWORDS = [
    'john deere', 'cnh', 'case ih', 'new holland', 'claas', 'kubota',
    'valtra', 'deutz-fahr', 'massey ferguson', 'electric tractor launch',
    'competitor', 'autonomous tractor patent', 'ev tractor',
]


# ============================================================
# E-TRACTOR INTELLIGENCE ENGINE
# ============================================================

class ETractorIntelligence:
    """
    Generates structured electric tractor business intelligence for Fendt/AGCO.
    Fully rule-based — no AI API calls required.
    """

    # ------------------------------------------------------------------
    # Signal filtering
    # ------------------------------------------------------------------

    def get_relevant_signals(self, signals: List[Dict]) -> List[Dict]:
        """Return signals relevant to e-tractors / subsidies."""
        result = []
        for sig in signals:
            text = f"{sig.get('title', '')} {sig.get('content', '')}".lower()
            if any(kw in text for kw in ETRACTOR_SIGNAL_KEYWORDS):
                result.append(sig)
        return result

    def get_competitor_signals(self, signals: List[Dict]) -> List[Dict]:
        """Return signals mentioning competitors."""
        result = []
        for sig in signals:
            text = f"{sig.get('title', '')} {sig.get('content', '')}".lower()
            if any(kw in text for kw in COMPETITOR_SIGNAL_KEYWORDS):
                result.append(sig)
        return result

    # ------------------------------------------------------------------
    # Subsidy analysis
    # ------------------------------------------------------------------

    def get_subsidy_programs(self, country: str) -> Dict:
        """Return static subsidy knowledge for a given country."""
        return SUBSIDY_KNOWLEDGE_BASE.get(country, {'programs': [], 'headline': 'No data available.'})

    def get_all_countries(self) -> List[str]:
        return list(SUBSIDY_KNOWLEDGE_BASE.keys())

    # ------------------------------------------------------------------
    # Business impact
    # ------------------------------------------------------------------

    def generate_business_impact(self, signals: List[Dict]) -> Dict:
        """Structured business impact from detected e-tractor signals."""
        relevant = self.get_relevant_signals(signals)
        critical_high = [s for s in relevant if s.get('disruption_classification') in ('CRITICAL', 'HIGH')]

        dim_counts: Dict[str, int] = {}
        for sig in relevant:
            dim = sig.get('primary_dimension', 'UNKNOWN')
            dim_counts[dim] = dim_counts.get(dim, 0) + 1

        avg_impact = (
            sum(s.get('impact_score') or 0 for s in relevant) / len(relevant)
            if relevant else 0
        )

        top_signals = sorted(
            relevant,
            key=lambda x: x.get('impact_score') or 0,
            reverse=True
        )[:5]

        overall_risk = 'HIGH' if len(critical_high) >= 3 else 'MODERATE' if len(critical_high) >= 1 else 'LOW'

        return {
            'total_relevant_signals': len(relevant),
            'critical_high_count': len(critical_high),
            'avg_impact_score': round(avg_impact, 2),
            'dimension_distribution': dim_counts,
            'top_signals': top_signals,
            'overall_risk_level': overall_risk,
        }

    # ------------------------------------------------------------------
    # Sales recommendations
    # ------------------------------------------------------------------

    def generate_sales_recommendations(self, signals: List[Dict]) -> List[Dict]:
        """Structured sales & commercial recommendations derived from signal intelligence."""
        relevant = self.get_relevant_signals(signals)
        competitor_sigs = self.get_competitor_signals(signals)

        comp_note = (
            f"{len(competitor_sigs)} competitor-related signals detected in intelligence feed — "
            "run competitive analysis on these immediately."
            if competitor_sigs
            else "No competitor signals in current database — expand scouting to competitor press releases."
        )

        top_signal_note = ""
        if relevant:
            top_sig = max(relevant, key=lambda x: x.get('impact_score') or 0)
            top_signal_note = (
                f'Live signal: "{top_sig["title"][:90]}..." '
                f'(Impact: {top_sig.get("impact_score", 0):.2f}, '
                f'Source: {top_sig.get("source", "N/A")})'
            )

        return [
            {
                'area': 'Revenue Planning',
                'priority': 'HIGH',
                'title': 'Target subsidy-ready segments first',
                'recommendation': (
                    'Prioritize sales pipeline in Germany (AFP 20–40%), France (PCAE 30–40%), '
                    'and Norway (Enova/Innovasjon Norge up to 45%). These markets have '
                    'accessible grant programs that reduce effective tractor cost significantly, '
                    'shortening farmer payback periods and enabling premium Fendt positioning.'
                ),
                'kpi': 'Net qualified pipeline value in subsidy-active markets by Q3 2025',
                'action': (
                    'Build a "Subsidy Net-Cost Calculator" for Fendt sales teams — '
                    'shows farmer their post-grant price in ≤60 seconds at point of sale.'
                ),
            },
            {
                'area': 'Market Establishment',
                'priority': 'HIGH',
                'title': 'Anchor fleet partnerships before 2026 CAP review',
                'recommendation': (
                    'Sign 5–10 anchor farm partnerships per target country for pilot fleet '
                    'deployment before 2026. CAP eco-scheme eligibility criteria will be '
                    're-negotiated in 2025–2026 — Fendt reference installations in pilot '
                    'programs can directly influence favorable classification criteria.'
                ),
                'kpi': '5 signed anchor farm MOUs per target country by end of 2025',
                'action': (
                    'Identify large (>300 ha) progressive operators via national farming '
                    'associations (DBV, FNSEA, NFU, Norsk Bondelag). Offer pilot terms '
                    'with service SLA and performance guarantee.'
                ),
            },
            {
                'area': 'Competitor Activity',
                'priority': 'CRITICAL',
                'title': 'Lock dealer network before competitor e-tractor commercialization',
                'recommendation': comp_note + (
                    ' John Deere (autonomous electric concept) and CNH (New Holland T7 Electric prototype) '
                    'signal 2026–2027 commercial timelines. Fendt must secure dealer network exclusivity '
                    'and e-tractor training certification before alternatives reach the market.'
                ),
                'kpi': '80% of top-tier Fendt dealers e-tractor certified by end of 2025',
                'action': (
                    'Launch "Fendt Electric Dealer" certification program: '
                    'service training, tooling investment support, and preferred commercial terms '
                    'tied to e-tractor sales targets. Prioritize dealers in subsidy-rich regions.'
                ),
            },
            {
                'area': 'Revenue Planning',
                'priority': 'MODERATE',
                'title': 'Develop Battery-as-a-Service (BaaS) commercial model',
                'recommendation': (
                    'The EU Battery Swapping Mandate (2027) creates infrastructure uncertainty '
                    'that Fendt can monetize. A BaaS or "Power Subscription" model reduces '
                    'upfront cost barrier, de-risks battery technology evolution for the farmer, '
                    'and creates a recurring revenue stream for Fendt. '
                    'Models from commercial EV trucking (Daimler, Volta) are the reference.'
                ),
                'kpi': 'BaaS model feasibility study completed Q3 2025; pilot with 3 farms by Q1 2026',
                'action': (
                    'Commission TCO modeling for BaaS vs. capital purchase scenarios. '
                    'Explore battery lease-back partnerships with energy companies '
                    '(E.ON, EnBW, EDF) who have rural grid interests.'
                ),
            },
            {
                'area': 'Market Intelligence',
                'priority': 'HIGH',
                'title': 'Live Signal Alert',
                'recommendation': top_signal_note if top_signal_note else 'No e-tractor signals currently in database — trigger a targeted intelligence sweep.',
                'kpi': 'Weekly signal briefing to sales leadership',
                'action': 'Run sentinel.py --run-once to refresh intelligence database.',
            },
        ]

    # ------------------------------------------------------------------
    # Marketing recommendations
    # ------------------------------------------------------------------

    def generate_marketing_recommendations(self) -> List[Dict]:
        """Structured marketing strategy, campaign, and communication recommendations."""
        return [
            {
                'category': 'Positioning Strategy',
                'priority': 'HIGH',
                'title': 'Reposition from "HP performance" to "Total Cost Efficiency + Sustainability"',
                'rationale': (
                    'Electric tractors compete on a fundamentally different value equation. '
                    'Farmers respond to ROI narratives. The traditional Fendt "performance leader" '
                    'positioning must evolve to address the economics of electrification.'
                ),
                'campaign_concept': (
                    '"The Math is Green" — data-driven campaign showing 10-year TCO '
                    'comparison (diesel vs. Fendt electric with subsidies). '
                    'Fendt e-tractor breaks even faster than perceived.'
                ),
                'channels': [
                    'Agricultural trade press (DLG Mitteilungen, Profi, Farming UK)',
                    'Agritechnica / SIMA / LAMMA booth messaging',
                    'Fendt.com product pages',
                ],
                'kpi': 'Brand perception shift in annual Fendt dealer survey: "best TCO" association',
            },
            {
                'category': 'Specific Campaign',
                'priority': 'HIGH',
                'title': '"Subsidy Navigator" — Digital Grant Eligibility Tool',
                'rationale': (
                    'Subsidy program complexity is the #1 non-price adoption barrier. '
                    'Farmers do not know what they can claim or how. '
                    'A tool that simplifies this creates pull demand and differentiates '
                    'Fendt from competitors who only sell hardware.'
                ),
                'campaign_concept': (
                    '"Your Subsidy, Calculated" — online configurator where farmers '
                    'select country, farm size, and tractor model → get personalized '
                    'grant eligibility + downloadable application guide + dealer contact. '
                    'Co-branded with national farm advisory services for trust.'
                ),
                'channels': [
                    'Fendt.com interactive configurator',
                    'Social media (Facebook/Instagram — primary channels for agricultural community)',
                    'Agricultural extension office and Chamber of Agriculture partnerships',
                ],
                'kpi': 'Tool interactions per month; qualified lead conversion rate from tool users',
            },
            {
                'category': 'Communication Measures',
                'priority': 'MODERATE',
                'title': 'Country-specific communication kits — localized by market',
                'rationale': (
                    'Subsidy programs, regulatory timelines, and farmer concerns differ '
                    'significantly by country. A single EU-wide message misses the '
                    'specificity that drives purchase decisions.'
                ),
                'campaign_concept': (
                    '"Fendt Electric, Made for [Country]" — regional content series with '
                    'local farmer testimonials, country-specific subsidy summaries, '
                    'and local dealer contacts. One version each for DE, FR, UK, NO.'
                ),
                'channels': [
                    'Country PR agencies + agricultural press',
                    'Agritechnica (DE), SIMA (FR), LAMMA (UK), Agri Nord (NO)',
                    'Local farming association newsletters and member communications',
                ],
                'kpi': 'Press coverage volume per country; dealer inquiry volume by market',
            },
            {
                'category': 'E-Tractor Specific',
                'priority': 'CRITICAL',
                'title': '"Fendt Electric Promise" — Address the 4 Adoption Barriers Proactively',
                'rationale': (
                    'E-tractor adoption barriers differ fundamentally from diesel. '
                    'Farmers lack EV reference points. If Fendt does not proactively address '
                    'range anxiety, charging, cold weather, and service concerns, '
                    'sales cycles extend by 12–18 months.'
                ),
                'campaign_concept': (
                    '4-part content series, one topic per quarter: '
                    '(1) Range — "Full Day. Every Day. Guaranteed." '
                    '(2) Charging — "We install it. You farm." '
                    '(3) Cold Weather — "Tested at −20°C. Built for Northern Europe." '
                    '(4) Service — "Your Fendt dealer, fully electric certified."'
                ),
                'channels': [
                    'YouTube (video testimonials + field demos)',
                    'Farming influencer partnerships (agricultural YouTubers: Clarkson\'s Farm, etc.)',
                    'Dealer point-of-sale materials and demo day events',
                ],
                'kpi': 'Content engagement rate; demo day conversion rate to qualified opportunity',
            },
        ]

    # ------------------------------------------------------------------
    # Customer needs comparison
    # ------------------------------------------------------------------

    def generate_etractor_customer_needs(self) -> List[Dict]:
        """
        Structured comparison of e-tractor specific needs vs. standard diesel tractor.
        Highlights where Fendt must adapt product, service, or marketing.
        """
        return [
            {
                'need_area': 'Range & Battery Life',
                'diesel_baseline': 'Continuous operation — refuel in minutes; no operational planning required.',
                'etractor_requirement': (
                    'Full 8–12 hour field cycle without mid-shift charging stop. '
                    'Battery sizing must cover peak harvest operations (>12h in summer). '
                    'Farmers will not accept range-limited machines during harvest window.'
                ),
                'fendt_implication': (
                    'Publish verified field-cycle range figures per major use case '
                    '(ploughing, spraying, transport). Battery sizing must match operational '
                    'reality, not theoretical maximums. Offer optional extended battery packs.'
                ),
                'risk_if_not_addressed': 'HIGH — #1 stated purchase barrier in all farmer EV surveys',
            },
            {
                'need_area': 'Charging Infrastructure',
                'diesel_baseline': 'Diesel available at farm suppliers, mobile refueling trucks for field use.',
                'etractor_requirement': (
                    'On-site 3-phase or DC fast charging required. '
                    'Rural grid capacity is often insufficient — grid upgrade costs can '
                    'exceed tractor premium. Charging logistics must fit farm workflow.'
                ),
                'fendt_implication': (
                    'Bundle infrastructure packages: tractor + charger + installation + '
                    'grid assessment. Partner with energy providers (E.ON, EDF, EnBW) for '
                    'rural grid upgrade co-financing. Offer mobile charging for field operations.'
                ),
                'risk_if_not_addressed': 'HIGH — Infrastructure cost is frequently cited as deal-breaker',
            },
            {
                'need_area': 'Cold Weather Performance',
                'diesel_baseline': 'Minor cold start issues; manageable with additives and preheating.',
                'etractor_requirement': (
                    'Lithium battery capacity degrades 20–40% below −10°C. '
                    'Critical for Norway, Northern Germany, Eastern France, Scottish uplands. '
                    'Battery heating systems add complexity and energy overhead.'
                ),
                'fendt_implication': (
                    'Market specifically validated cold-weather battery management. '
                    'Warrant performance down to −20°C. Publish independent cold-weather '
                    'test results. This is a critical differentiator for Northern European markets.'
                ),
                'risk_if_not_addressed': 'HIGH — Blocks adoption in Norway and Northern Germany (key e-tractor markets)',
            },
            {
                'need_area': 'PTO (Power Take-Off) Compatibility',
                'diesel_baseline': 'Universal PTO standard; backward compatible with all existing implements.',
                'etractor_requirement': (
                    'Electric PTO is a different power delivery architecture. '
                    'Farmers have €100,000s invested in existing implements. '
                    'Compatibility uncertainty delays purchase decisions significantly.'
                ),
                'fendt_implication': (
                    'Publish comprehensive validated implement compatibility list before launch. '
                    'Develop universal e-PTO adapter program for legacy implements. '
                    'This is a critical purchase decision factor — don\'t leave it to dealers.'
                ),
                'risk_if_not_addressed': 'MODERATE — Extends sales cycle by 6–12 months while farmers research',
            },
            {
                'need_area': 'After-Sales & Service Availability',
                'diesel_baseline': 'Diesel mechanics widely available; parts standardized and interchangeable.',
                'etractor_requirement': (
                    'Electric drivetrain requires specialist training. '
                    'Battery pack replacement is a major unknown cost. '
                    'Farmers fear being stranded during harvest — no backup during downtime.'
                ),
                'fendt_implication': (
                    'Deploy Fendt Electric certified service program for all dealer network. '
                    'Offer battery health monitoring via FendtONE with proactive service alerts. '
                    'Provide backup machine guarantee for critical peak periods (72h response).'
                ),
                'risk_if_not_addressed': 'HIGH — Service fear is the #2 adoption barrier after range anxiety',
            },
            {
                'need_area': 'Total Cost of Ownership Transparency',
                'diesel_baseline': 'Well-understood TCO model — fuel cost, predictable service intervals.',
                'etractor_requirement': (
                    'Farmers lack EV reference points. Battery degradation rates, '
                    'electricity cost variability, subsidy uncertainty, and resale value '
                    'unknowns create significant purchase hesitancy.'
                ),
                'fendt_implication': (
                    'Provide 7-year financial modeling tools with subsidy scenarios. '
                    'Offer TCO guarantee program (performance bond) for early adopters. '
                    'Publish independently verified resale value projections from Fendt Financial.'
                ),
                'risk_if_not_addressed': 'HIGH — Prolongs sales cycle; farmers default to diesel when uncertain',
            },
        ]
