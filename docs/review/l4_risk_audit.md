# L4 — Auditoría de deduplicación de riesgos (VISTA PARA REVISIÓN HUMANA)

> Generado el 2026-06-09. **No se ha borrado ni modificado nada** de `outputs/intermediate/{TICKER}_L4.json`. Es solo una vista para que cuentes contra el filing real; **el número final lo decides tú**.

> Dos vistas complementarias:
> - **Vista A (estructural, la más útil):** riesgos agrupados por el *sub-header* del chunk de origen (`chunks[].subheader`), que corresponde a los encabezados en negrita de Item 1A — es decir, a los factores de riesgo reales del filing. Si un sub-header genera muchos riesgos, es fragmentación.
> - **Vista B (textual):** grupos por similitud de título+summary (difflib ≥0.72); detecta duplicados casi-literales y el solape de chunks (⚠️overlap = chunks 1A_NNN adyacentes).


## Resumen de conteos

| Ticker | Crudo | Sub-headers (Vista A, proxy factores reales) | Grupos textuales (Vista B) | Grupos dup textuales |
|---|---|---|---|---|
| AAPL | 68 | 26 | 64 | 2 |
| JPM | 105 | 52 | 93 | 9 |

> Ninguno de estos números está validado: son heurísticos. Para AAPL, compara los **sub-headers de la Vista A** con los factores en negrita del Item 1A real (~20-30 esperados) antes de fijar el conteo.


## AAPL

- Riesgos crudos: **68**
- **Vista A** — sub-headers distintos que generan riesgos: **26** (proxy del nº de factores reales del filing)
- **Vista B** — grupos textuales: **64**; grupos con ≥2 miembros: **2** (afectan a 6 riesgos)

### Vista A — riesgos por sub-header de Item 1A (cuenta esto contra el filing)

| # riesgos | Sub-header (factor de riesgo del filing) | chunks |
|---|---|---|
| 5 | Future operating results depend upon the Company’s ability to obtain components … | 1A_009 |
| 5 | The Company depends on the performance of carriers and other resellers. | 1A_016 |
| 5 | Investment in new business strategies, commercial relationships and acquisitions… | 1A_019 |
| 5 | The Company’s business is subject to a variety of U.S. and international laws, r… | 1A_025 |
| 4 | The Company’s business can be impacted by political events, trade and other inte… | 1A_004 |
| 4 | Global markets for the Company’s products and services are highly competitive an… | 1A_005 |
| 4 | The Company’s products and services may be affected from time to time by design … | 1A_010 |
| 4 | The Company’s success depends largely on the talents and efforts of its team mem… | 1A_015 |
| 3 | The Company’s operations and performance depend significantly on global and regi… | 1A_003 |
| 3 | To remain competitive and stimulate customer demand, the Company must successful… | 1A_007 |
| 3 | Losses or unauthorized access to or releases of confidential information, includ… | 1A_018 |
| 3 | The technology industry, including, in some instances, the Company, is subject t… | 1A_024 |
| 3 | The Company’s financial performance is subject to risks associated with changes … | 1A_028 |
| 3 | The Company is subject to changes in tax rates, the adoption of new U.S. or inte… | 1A_031 |
| 2 | The Company is subject to complex and changing laws and regulations worldwide, w… | 1A_022 |
| 2 | The Company is exposed to credit risk and fluctuations in the values of its inve… | 1A_029 |
| 1 | The Company depends on component and product manufacturing and logistical servic… | 1A_008 |
| 1 | The Company is exposed to the risk of write-downs on the value of its inventory … | 1A_011 |
| 1 | The Company relies on access to third-party intellectual property, which may not… | 1A_012 |
| 1 | The Company’s future performance depends in part on support from third-party sof… | 1A_013 |
| 1 | Failure to obtain or create digital content that appeals to the Company’s custom… | 1A_014 |
| 1 | The Company’s business and reputation are impacted by information technology sys… | 1A_017 |
| 1 | Varied stakeholder expectations about social and other issues expose the Company… | 1A_023 |
| 1 | The Company’s net sales and gross margins are subject to volatility and downward… | 1A_027 |
| 1 | The Company is exposed to credit risk on its trade accounts receivable, vendor n… | 1A_030 |
| 1 | The price of the Company’s stock is subject to volatility. | 1A_033 |

<details><summary>Vista A — detalle de riesgos por sub-header</summary>

**Future operating results depend upon the Company’s ability to obtain components in sufficient quantities on commercially reasonable terms.** (5 riesgos)
  - `R-AAPL-016` [1A_009] Riesgo de suministro
  - `R-AAPL-017` [1A_009] Riesgo de escasez de componentes
  - `R-AAPL-018` [1A_009] Riesgo de precios
  - `R-AAPL-019` [1A_009] Riesgo de capacidad de producción
  - `R-AAPL-020` [1A_009] Riesgo de renovación de contratos

**The Company depends on the performance of carriers and other resellers.** (5 riesgos)
  - `R-AAPL-033` [1A_016] Dependencia de los proveedores
  - `R-AAPL-034` [1A_016] Cambios en las preferencias y comportamientos de los consumidores
  - `R-AAPL-035` [1A_016] Condición financiera debilitada de los vendedores
  - `R-AAPL-036` [1A_016] Reducción en el orden y marketing por parte de los vendedores
  - `R-AAPL-037` [1A_016] Inversión en programas sin asegurar retorno

**Investment in new business strategies, commercial relationships and acquisitions could disrupt the Company’s ongoing business, present risks not originally contemplated, and materially adversely affect the Company’s business, reputation, results of operations and financial condition.** (5 riesgos)
  - `R-AAPL-042` [1A_019] Inversion en nuevas estrategias de negocios
  - `R-AAPL-043` [1A_019] Relaciones comerciales y adquisiciones
  - `R-AAPL-044` [1A_019] Aprobación regulatoria
  - `R-AAPL-045` [1A_019] Desempeño del socio o parte contraria
  - `R-AAPL-046` [1A_019] Éxito de las estrategias y inversiones

**The Company’s business is subject to a variety of U.S. and international laws, rules, policies and other obligations regarding the collection, use, protection and transfer of personal data.** (5 riesgos)
  - `R-AAPL-053` [1A_025] Regulaciones de privacidad y protección de datos
  - `R-AAPL-054` [1A_025] Incumplimiento de declaraciones públicas sobre privacidad
  - `R-AAPL-055` [1A_025] Disclosures inadvertidas de datos personales
  - `R-AAPL-056` [1A_025] Regulaciones específicas para datos de menores
  - `R-AAPL-057` [1A_025] Regulaciones de seguridad en línea

**The Company’s business can be impacted by political events, trade and other international disputes, geopolitical tensions, conflict, terrorism, natural disasters, public health issues, industrial accidents and other business interruptions.** (4 riesgos)
  - `R-AAPL-004` [1A_004] Conflict
  - `R-AAPL-005` [1A_004] Trade restrictions
  - `R-AAPL-006` [1A_004] Natural disasters
  - `R-AAPL-007` [1A_004] Public health issues

**Global markets for the Company’s products and services are highly competitive and subject to rapid technological change, and the Company may be unable to compete effectively in these markets.** (4 riesgos)
  - `R-AAPL-008` [1A_005] Competencia en mercados globales
  - `R-AAPL-009` [1A_005] Presión por el cambio tecnológico
  - `R-AAPL-010` [1A_005] Infracción de derechos de propiedad intelectual
  - `R-AAPL-011` [1A_005] Competencia intensificada

**The Company’s products and services may be affected from time to time by design and manufacturing defects that could materially adversely affect the Company’s business and result in harm to the Company’s reputation.** (4 riesgos)
  - `R-AAPL-021` [1A_010] Defects en productos y servicios
  - `R-AAPL-022` [1A_010] Problemas de calidad en servicios
  - `R-AAPL-023` [1A_010] Riesgos de seguridad y privacidad
  - `R-AAPL-024` [1A_010] Reclamaciones de responsabilidad por productos

**The Company’s success depends largely on the talents and efforts of its team members, the continued service and availability of highly skilled employees, including key personnel, and the Company’s ability to nurture its distinctive and inclusive culture.** (4 riesgos)
  - `R-AAPL-029` [1A_015] Competencia por talento
  - `R-AAPL-030` [1A_015] Cambio en las dinámicas del trabajo
  - `R-AAPL-031` [1A_015] Regulaciones laborales y de inmigración
  - `R-AAPL-032` [1A_015] Cultura empresarial

**The Company’s operations and performance depend significantly on global and regional economic conditions and adverse economic conditions can materially adversely affect the Company’s business, results of operations, financial condition and stock price.** (3 riesgos)
  - `R-AAPL-001` [1A_003] Condiciones económicas adversas
  - `R-AAPL-002` [1A_003] Desestabilización financiera
  - `R-AAPL-003` [1A_003] Riesgo de crédito

**To remain competitive and stimulate customer demand, the Company must successfully manage frequent introductions and transitions of products and services.** (3 riesgos)
  - `R-AAPL-012` [1A_007] Introducción y transición de productos y servicios
  - `R-AAPL-013` [1A_007] Competencia y demanda del cliente
  - `R-AAPL-014` [1A_007] Recruitment and retention of skilled personnel

**Losses or unauthorized access to or releases of confidential information, including personal information, could subject the Company to significant reputational, financial, legal and operational consequences.** (3 riesgos)
  - `R-AAPL-039` [1A_018] Perdida de información confidencial
  - `R-AAPL-040` [1A_018] Ataques cibernéticos
  - `R-AAPL-041` [1A_018] Riesgo de seguridad

**The technology industry, including, in some instances, the Company, is subject to intense media, political and regulatory scrutiny, which exposes the Company to increasing regulation, government investigations, legal actions and penalties.** (3 riesgos)
  - `R-AAPL-050` [1A_024] Regulación
  - `R-AAPL-051` [1A_024] Investigaciones y acciones legales
  - `R-AAPL-052` [1A_024] Cambios en las prácticas de negocio

**The Company’s financial performance is subject to risks associated with changes in the value of the U.S. dollar relative to local currencies.** (3 riesgos)
  - `R-AAPL-059` [1A_028] Fluctuaciones en las tasas de cambio
  - `R-AAPL-060` [1A_028] Efectos negativos en los márgenes brutos
  - `R-AAPL-061` [1A_028] Efectos limitados de las herramientas de hedge

**The Company is subject to changes in tax rates, the adoption of new U.S. or international tax legislation and exposure to additional tax liabilities.** (3 riesgos)
  - `R-AAPL-065` [1A_031] Cambios en tasas impositivas
  - `R-AAPL-066` [1A_031] Adopción de nuevas leyes fiscales
  - `R-AAPL-067` [1A_031] Exposición a responsabilidades fiscales adicionales

**The Company is subject to complex and changing laws and regulations worldwide, which exposes the Company to potential liabilities, increased costs and other adverse effects on the Company’s business.** (2 riesgos)
  - `R-AAPL-047` [1A_022] Regulaciones cambiantes
  - `R-AAPL-048` [1A_022] Exportaciones e importaciones

**The Company is exposed to credit risk and fluctuations in the values of its investment portfolio.** (2 riesgos)
  - `R-AAPL-062` [1A_029] Riesgo crediticio
  - `R-AAPL-063` [1A_029] Fluctuaciones en el valor de la cartera de inversiones

**The Company depends on component and product manufacturing and logistical services provided by outsourcing partners, many of which are located outside of the U.S.** (1 riesgos)
  - `R-AAPL-015` [1A_008] Dependencia de terceros

**The Company is exposed to the risk of write-downs on the value of its inventory and other assets, in addition to purchase commitment cancellation risk.** (1 riesgos)
  - `R-AAPL-025` [1A_011] Riesgo de write-downs en inventarios y otros activos

**The Company relies on access to third-party intellectual property, which may not be available to the Company on commercially reasonable terms, or at all.** (1 riesgos)
  - `R-AAPL-026` [1A_012] Acceso a propiedad intelectual de terceros

**The Company’s future performance depends in part on support from third-party software developers.** (1 riesgos)
  - `R-AAPL-027` [1A_013] Dependencia de terceros en el desarrollo y mantenimiento de software

**Failure to obtain or create digital content that appeals to the Company’s customers, or to make such content available on commercially reasonable terms, could have a material adverse impact on the Company’s business, results of operations and financial condition.** (1 riesgos)
  - `R-AAPL-028` [1A_014] Contenido digital no atractivo

**The Company’s business and reputation are impacted by information technology system failures and network disruptions.** (1 riesgos)
  - `R-AAPL-038` [1A_017] Fallos de sistemas de tecnología de la información

**Varied stakeholder expectations about social and other issues expose the Company to potential liabilities, increased costs, reputational harm, and other adverse effects on the Company’s business.** (1 riesgos)
  - `R-AAPL-049` [1A_023] Expectativas de los stakeholders

**The Company’s net sales and gross margins are subject to volatility and downward pressure due to a variety of factors.** (1 riesgos)
  - `R-AAPL-058` [1A_027] Presiones de precios globales

**The Company is exposed to credit risk on its trade accounts receivable, vendor non-trade receivables and prepayments related to long-term supply agreements, and this risk is heightened during periods when economic conditions worsen.** (1 riesgos)
  - `R-AAPL-064` [1A_030] Riesgo de crédito

**The price of the Company’s stock is subject to volatility.** (1 riesgos)
  - `R-AAPL-068` [1A_033] Volatilidad del precio de la acción

</details>

### Vista B — candidatos a duplicado textual (grupos ≥2)

**AAPL-B1** — 4 riesgos ⚠️overlap
  - `R-AAPL-003` [1A_003] **Riesgo de crédito**
  - `R-AAPL-018` [1A_009] **Riesgo de precios**
  - `R-AAPL-062` [1A_029] **Riesgo crediticio**
  - `R-AAPL-064` [1A_030] **Riesgo de crédito**

**AAPL-B2** — 2 riesgos
  - `R-AAPL-023` [1A_010] **Riesgos de seguridad y privacidad**
  - `R-AAPL-041` [1A_018] **Riesgo de seguridad**


## JPM

- Riesgos crudos: **105**
- **Vista A** — sub-headers distintos que generan riesgos: **52** (proxy del nº de factores reales del filing)
- **Vista B** — grupos textuales: **93**; grupos con ≥2 miembros: **9** (afectan a 21 riesgos)

### Vista A — riesgos por sub-header de Item 1A (cuenta esto contra el filing)

| # riesgos | Sub-header (factor de riesgo del filing) | chunks |
|---|---|---|
| 9 | JPMorganChase could incur losses arising from any significant inadequacy or laps… | 1A_045 |
| 6 | Operational | 1A_008 |
| 6 | JPMorganChase could be negatively affected by adverse changes in the financial c… | 1A_029 |
| 5 | Differences in the supervision and regulation of financial services firms could … | 1A_016 |
| 5 | Unfavorable market and economic conditions could adversely affect JPMorganChase’… | 1A_026 |
| 5 | JPMorganChase’s operations, results, and competitive standing could be adversely… | 1A_050 |
| 4 | JPMorganChase’s consumer businesses could be negatively affected by adverse econ… | 1A_025 |
| 4 | JPMorganChase’s results could be materially affected by market fluctuations and … | 1A_028 |
| 4 | Damage to JPMorganChase’s reputation could negatively affect its business, resul… | 1A_053 |
| 4 | Various factors could impact JPMorganChase’s workforce. | 1A_057 |
| 3 | JPMorgan Chase & Co. is a holding company and depends on its subsidiaries for fu… | 1A_033 |
| 3 | Failure to effectively manage potential conflicts of interest or to satisfy fidu… | 1A_054 |
| 2 | JPMorganChase’s businesses could be negatively affected by economic uncertainty … | 1A_023 |
| 2 | Adverse economic and market events and conditions could negatively affect JPMorg… | 1A_024 |
| 2 | Changes in interest rates and credit spreads could adversely affect JPMorganChas… | 1A_027 |
| 2 | A successful cyber attack could cause significant harm to JPMorganChase and its … | 1A_038 |
| 2 | JPMorganChase could recognize unexpected losses, its capital levels could be red… | 1A_046 |
| 2 | The effects of climate change could adversely affect JPMorganChase’s business an… | 1A_051 |
| 2 | An outbreak or escalation of hostilities between countries or within a country o… | 1A_055 |
| 1 | Legal and Regulatory | 1A_002 |
| 1 | Political | 1A_003 |
| 1 | Market | 1A_004 |
| 1 | Credit | 1A_005 |
| 1 | Liquidity | 1A_006 |
| 1 | Capital | 1A_007 |
| 1 | Strategic | 1A_009 |
| 1 | Conduct | 1A_010 |
| 1 | Reputation | 1A_011 |
| 1 | Country | 1A_012 |
| 1 | JPMorganChase’s businesses are highly regulated and are significantly affected b… | 1A_015 |
| 1 | JPMorganChase faces significant legal risks from civil and governmental proceedi… | 1A_017 |
| 1 | Resolving an investigation by a governmental authority could subject JPMorganCha… | 1A_018 |
| 1 | JPMorganChase’s compliance risk and operating costs could be higher in jurisdict… | 1A_019 |
| 1 | JPMorganChase's business and operations could be negatively affected by governme… | 1A_020 |
| 1 | Changes in the requirements for the regulatory evaluation of JPMorganChase’s res… | 1A_021 |
| 1 | Holders of JPMorgan Chase & Co.’s debt and equity securities will absorb losses … | 1A_022 |
| 1 | JPMorganChase could suffer losses if the value of collateral declines. | 1A_030 |
| 1 | JPMorganChase’s ability to operate its businesses could be impaired if its liqui… | 1A_032 |
| 1 | JPMorganChase’s liquidity and cost of funding could be adversely affected by dow… | 1A_034 |
| 1 | JPMorganChase’s ability to distribute capital to shareholders, and to support it… | 1A_035 |
| 1 | JPMorganChase’s businesses could be adversely affected by the failure or disrupt… | 1A_036 |
| 1 | JPMorganChase’s interconnectedness with clients, customers and other external pa… | 1A_037 |
| 1 | JPMorganChase’s businesses could be adversely affected if it fails to identify a… | 1A_039 |
| 1 | JPMorganChase’s business and operations rely on appropriate staffing and on the … | 1A_040 |
| 1 | JPMorganChase faces substantial legal and operational risks related to the proce… | 1A_041 |
| 1 | JPMorganChase’s operations, results and reputation could be harmed by occurrence… | 1A_042 |
| 1 | Any failure to maintain adequate data management processes could adversely affec… | 1A_043 |
| 1 | Enhanced regulatory and other standards for the oversight of JPMorganChase’s ven… | 1A_044 |
| 1 | A significant inadequacy in disclosure or financial reporting controls could neg… | 1A_047 |
| 1 | JPMorganChase’s results or competitive standing could suffer if its management f… | 1A_048 |
| 1 | Competition in the financial services industry could lead to negative effects on… | 1A_049 |
| 1 | Conduct failure by JPMorganChase employees could trigger litigation and regulato… | 1A_052 |

<details><summary>Vista A — detalle de riesgos por sub-header</summary>

**JPMorganChase could incur losses arising from any significant inadequacy or lapse in its risk management framework and control environment.** (9 riesgos)
  - `R-JPM-071` [1A_045] Inadequacy in risk management framework
  - `R-JPM-072` [1A_045] Inaccurate identification of risks
  - `R-JPM-073` [1A_045] Delayed escalation of risk issues
  - `R-JPM-074` [1A_045] Negative business decisions
  - `R-JPM-075` [1A_045] Harm to customers or clients
  - `R-JPM-076` [1A_045] Significant resource allocation
  - `R-JPM-077` [1A_045] Non-compliance with laws
  - `R-JPM-078` [1A_045] Litigation and investigations
  - `R-JPM-079` [1A_045] Reputational harm

**Operational** (6 riesgos)
  - `R-JPM-007` [1A_008] Riesgos operacionales
  - `R-JPM-008` [1A_008] Riesgos de sistemas y empleados
  - `R-JPM-009` [1A_008] Riesgos cibernéticos
  - `R-JPM-010` [1A_008] Riesgos de gestión de datos
  - `R-JPM-011` [1A_008] Riesgos de cumplimiento con estándares de supervisión de proveedores
  - `R-JPM-012` [1A_008] Riesgos del marco de gestión de riesgos

**JPMorganChase could be negatively affected by adverse changes in the financial condition of clients, counterparties, CCPs and other market participants.** (6 riesgos)
  - `R-JPM-048` [1A_029] default de clientes y contrapartes
  - `R-JPM-049` [1A_029] insolvencia de entidades custodiales
  - `R-JPM-050` [1A_029] default de CCPs
  - `R-JPM-051` [1A_029] default de miembros de CCPs
  - `R-JPM-052` [1A_029] perdidas de custodia
  - `R-JPM-053` [1A_029] actividad fraudulenta de clientes

**Differences in the supervision and regulation of financial services firms could require JPMorganChase to modify its operations and incur higher operational and compliance costs.** (5 riesgos)
  - `R-JPM-018` [1A_016] Modificación de operaciones
  - `R-JPM-019` [1A_016] Costos operativos y de cumplimiento
  - `R-JPM-020` [1A_016] Competencia desigual
  - `R-JPM-021` [1A_016] Conflictos legales
  - `R-JPM-022` [1A_016] Requisitos operativos y estructurales

**Unfavorable market and economic conditions could adversely affect JPMorganChase’s wholesale businesses.** (5 riesgos)
  - `R-JPM-037` [1A_026] Condiciones de mercado y económicas desfavorables
  - `R-JPM-038` [1A_026] Disminución de los ingresos por comisiones
  - `R-JPM-039` [1A_026] Salidas masivas de fondos
  - `R-JPM-040` [1A_026] Perjuicios crediticios
  - `R-JPM-041` [1A_026] Impacto en el rendimiento de los préstamos comerciales

**JPMorganChase’s operations, results, and competitive standing could be adversely affected by the development of advanced technologies such as AI.** (5 riesgos)
  - `R-JPM-085` [1A_050] Fallos de sistemas de IA
  - `R-JPM-086` [1A_050] Exposición a ataques cibernéticos
  - `R-JPM-087` [1A_050] Riesgos regulatorios y de cumplimiento
  - `R-JPM-088` [1A_050] Desventaja competitiva
  - `R-JPM-089` [1A_050] Reemplazo o desintermediación de relaciones con clientes

**JPMorganChase’s consumer businesses could be negatively affected by adverse economic conditions and adverse impacts of governmental policies.** (4 riesgos)
  - `R-JPM-033` [1A_025] Condiciones económicas adversas
  - `R-JPM-034` [1A_025] Incremento en la morosidad
  - `R-JPM-035` [1A_025] Reducción en la demanda de productos y servicios
  - `R-JPM-036` [1A_025] Impacto de las políticas gubernamentales

**JPMorganChase’s results could be materially affected by market fluctuations and significant changes in the valuation of financial instruments.** (4 riesgos)
  - `R-JPM-044` [1A_028] Fluctuaciones del mercado
  - `R-JPM-045` [1A_028] Valuación de instrumentos financieros
  - `R-JPM-046` [1A_028] Disposición de instrumentos financieros
  - `R-JPM-047` [1A_028] Estrategias de gestión del riesgo

**Damage to JPMorganChase’s reputation could negatively affect its business, results and prospects.** (4 riesgos)
  - `R-JPM-093` [1A_053] Daño a la reputación
  - `R-JPM-094` [1A_053] Percepción incorrecta
  - `R-JPM-095` [1A_053] Investigaciones gubernamentales
  - `R-JPM-096` [1A_053] Perdida de clientes y empleados

**Various factors could impact JPMorganChase’s workforce.** (4 riesgos)
  - `R-JPM-102` [1A_057] Recruitment
  - `R-JPM-103` [1A_057] Succession Planning
  - `R-JPM-104` [1A_057] Immigration Policies
  - `R-JPM-105` [1A_057] Workforce Displacement

**JPMorgan Chase & Co. is a holding company and depends on its subsidiaries for funding to make payments on its outstanding securities.** (3 riesgos)
  - `R-JPM-056` [1A_033] Dependencia de la matriz sobre sus subsidiarias para el pago de obligaciones financieras
  - `R-JPM-057` [1A_033] Limitaciones en el pago de dividendos
  - `R-JPM-058` [1A_033] Bancarrota y procedimientos de resolución

**Failure to effectively manage potential conflicts of interest or to satisfy fiduciary obligations could result in litigation and enforcement actions and cause reputational harm.** (3 riesgos)
  - `R-JPM-097` [1A_054] Conflictos de interés
  - `R-JPM-098` [1A_054] Identificación y gestión de conflictos
  - `R-JPM-099` [1A_054] Cumplimiento con obligaciones fiduciarias

**JPMorganChase’s businesses could be negatively affected by economic uncertainty resulting from political and geopolitical developments.** (2 riesgos)
  - `R-JPM-029` [1A_023] Desarrollo político y geopolítico
  - `R-JPM-030` [1A_023] Políticas monetarias

**Adverse economic and market events and conditions could negatively affect JPMorganChase’s results of operations and investment and market-making positions.** (2 riesgos)
  - `R-JPM-031` [1A_024] Economía y mercados adversos
  - `R-JPM-032` [1A_024] Cambios económicos

**Changes in interest rates and credit spreads could adversely affect JPMorganChase’s earnings or its liquidity and capital levels.** (2 riesgos)
  - `R-JPM-042` [1A_027] Cambios en tasas de interés
  - `R-JPM-043` [1A_027] Aumento de las tasas de interés

**A successful cyber attack could cause significant harm to JPMorganChase and its clients and customers.** (2 riesgos)
  - `R-JPM-063` [1A_038] Ataque cibernético exitoso
  - `R-JPM-064` [1A_038] Brechas de seguridad

**JPMorganChase could recognize unexpected losses, its capital levels could be reduced and it could face greater regulatory scrutiny if its models, estimations or judgments, including those used in its financial statements, are inadequate or incorrect.** (2 riesgos)
  - `R-JPM-080` [1A_046] Modelos y estimaciones inadecuados o incorrectos
  - `R-JPM-081` [1A_046] Limitaciones en la precisión de los modelos

**The effects of climate change could adversely affect JPMorganChase’s business and operations, both directly and as a result of impacts on its clients and customers.** (2 riesgos)
  - `R-JPM-090` [1A_051] Riesgos físicos del cambio climático
  - `R-JPM-091` [1A_051] Riesgos de transición del cambio climático

**An outbreak or escalation of hostilities between countries or within a country or region could have a material adverse effect on the global economy and on JPMorganChase’s businesses within the affected region or globally.** (2 riesgos)
  - `R-JPM-100` [1A_055] Conflict
  - `R-JPM-101` [1A_055] Cyber attacks

**Legal and Regulatory** (1 riesgos)
  - `R-JPM-001` [1A_002] Riesgos legales y regulatorios

**Political** (1 riesgos)
  - `R-JPM-002` [1A_003] Riesgos políticos

**Market** (1 riesgos)
  - `R-JPM-003` [1A_004] Riesgos económicos y de mercado

**Credit** (1 riesgos)
  - `R-JPM-004` [1A_005] Riesgo crediticio

**Liquidity** (1 riesgos)
  - `R-JPM-005` [1A_006] Riesgo de liquidez

**Capital** (1 riesgos)
  - `R-JPM-006` [1A_007] Riesgo de capital

**Strategic** (1 riesgos)
  - `R-JPM-013` [1A_009] Riesgos estratégicos

**Conduct** (1 riesgos)
  - `R-JPM-014` [1A_010] Conduct

**Reputation** (1 riesgos)
  - `R-JPM-015` [1A_011] Reputación

**Country** (1 riesgos)
  - `R-JPM-016` [1A_012] Riesgos por país

**JPMorganChase’s businesses are highly regulated and are significantly affected by applicable law and supervisory expectations.** (1 riesgos)
  - `R-JPM-017` [1A_015] Regulación y supervisión

**JPMorganChase faces significant legal risks from civil and governmental proceedings, including litigation, investigations and enforcement actions.** (1 riesgos)
  - `R-JPM-023` [1A_017] Riesgos legales

**Resolving an investigation by a governmental authority could subject JPMorganChase to significant penalties and other repercussions.** (1 riesgos)
  - `R-JPM-024` [1A_018] Penalizaciones significativas

**JPMorganChase’s compliance risk and operating costs could be higher in jurisdictions with less predictable legal, regulatory and judicial frameworks.** (1 riesgos)
  - `R-JPM-025` [1A_019] Riesgo de cumplimiento y costos operativos

**JPMorganChase's business and operations could be negatively affected by governmental policies that discourage or penalize doing business with certain industries or that require specific business practices.** (1 riesgos)
  - `R-JPM-026` [1A_020] Políticas gubernamentales

**Changes in the requirements for the regulatory evaluation of JPMorganChase’s resolution plan could increase its funding or operational costs or require restructuring or curtailment of its businesses.** (1 riesgos)
  - `R-JPM-027` [1A_021] Cambio en los requisitos de evaluación regulatoria del plan de resolución

**Holders of JPMorgan Chase & Co.’s debt and equity securities will absorb losses if it were to enter into a resolution.** (1 riesgos)
  - `R-JPM-028` [1A_022] Perdidas para los tenedores de bonos y acciones

**JPMorganChase could suffer losses if the value of collateral declines.** (1 riesgos)
  - `R-JPM-054` [1A_030] Bajada en el valor del colateral

**JPMorganChase’s ability to operate its businesses could be impaired if its liquidity is constrained.** (1 riesgos)
  - `R-JPM-055` [1A_032] Constricción de liquidez

**JPMorganChase’s liquidity and cost of funding could be adversely affected by downgrades in its credit ratings.** (1 riesgos)
  - `R-JPM-059` [1A_034] Downgrade en calificaciones de crédito

**JPMorganChase’s ability to distribute capital to shareholders, and to support its business activities could be limited if it does not satisfy applicable regulatory capital requirements.** (1 riesgos)
  - `R-JPM-060` [1A_035] Limitación de distribución de capital

**JPMorganChase’s businesses could be adversely affected by the failure or disruption of operational systems on which they depend.** (1 riesgos)
  - `R-JPM-061` [1A_036] Fallas o interrupciones en los sistemas operativos

**JPMorganChase’s interconnectedness with clients, customers and other external parties could be a source of significant operational risk.** (1 riesgos)
  - `R-JPM-062` [1A_037] Riesgo operacional

**JPMorganChase’s businesses could be adversely affected if it fails to identify and address operational risks associated with the introduction of or changes to products, services, delivery platforms or technologies.** (1 riesgos)
  - `R-JPM-065` [1A_039] Riesgo operacional

**JPMorganChase’s business and operations rely on appropriate staffing and on the competence, trustworthiness, health and safety of employees.** (1 riesgos)
  - `R-JPM-066` [1A_040] Staffing shortages

**JPMorganChase faces substantial legal and operational risks related to the processing and safeguarding of personal information.** (1 riesgos)
  - `R-JPM-067` [1A_041] Riesgos legales y operativos relacionados con la protección de información personal

**JPMorganChase’s operations, results and reputation could be harmed by occurrences of extraordinary events beyond its control.** (1 riesgos)
  - `R-JPM-068` [1A_042] Ataques cibernéticos

**Any failure to maintain adequate data management processes could adversely affect JPMorganChase’s ability to effectively manage its businesses, comply with applicable law or make informed business decisions.** (1 riesgos)
  - `R-JPM-069` [1A_043] Fallos en los procesos de gestión de datos

**Enhanced regulatory and other standards for the oversight of JPMorganChase’s vendors and other service providers could result in higher costs and other potential exposures.** (1 riesgos)
  - `R-JPM-070` [1A_044] Costos más altos

**A significant inadequacy in disclosure or financial reporting controls could negatively affect JPMorganChase’s business, operations and reputation.** (1 riesgos)
  - `R-JPM-082` [1A_047] Inadequacy in disclosure or financial reporting controls

**JPMorganChase’s results or competitive standing could suffer if its management fails to develop and execute effective business strategies and to anticipate changes affecting those strategies.** (1 riesgos)
  - `R-JPM-083` [1A_048] Desarrollo e implementación de estrategias empresariales

**Competition in the financial services industry could lead to negative effects on JPMorganChase’s results of operations.** (1 riesgos)
  - `R-JPM-084` [1A_049] Competencia en el sector financiero

**Conduct failure by JPMorganChase employees could trigger litigation and regulatory actions and harm JPMorganChase’s reputation.** (1 riesgos)
  - `R-JPM-092` [1A_052] Conduct failure

</details>

### Vista B — candidatos a duplicado textual (grupos ≥2)

**JPM-B1** — 4 riesgos
  - `R-JPM-007` [1A_008] **Riesgos operacionales**
  - `R-JPM-023` [1A_017] **Riesgos legales**
  - `R-JPM-062` [1A_037] **Riesgo operacional**
  - `R-JPM-065` [1A_039] **Riesgo operacional**

**JPM-B2** — 3 riesgos
  - `R-JPM-010` [1A_008] **Riesgos de gestión de datos**
  - `R-JPM-012` [1A_008] **Riesgos del marco de gestión de riesgos**
  - `R-JPM-069` [1A_043] **Fallos en los procesos de gestión de datos**

**JPM-B3** — 2 riesgos
  - `R-JPM-002` [1A_003] **Riesgos políticos**
  - `R-JPM-016` [1A_012] **Riesgos por país**

**JPM-B4** — 2 riesgos
  - `R-JPM-019` [1A_016] **Costos operativos y de cumplimiento**
  - `R-JPM-087` [1A_050] **Riesgos regulatorios y de cumplimiento**

**JPM-B5** — 2 riesgos
  - `R-JPM-026` [1A_020] **Políticas gubernamentales**
  - `R-JPM-036` [1A_025] **Impacto de las políticas gubernamentales**

**JPM-B6** — 2 riesgos
  - `R-JPM-042` [1A_027] **Cambios en tasas de interés**
  - `R-JPM-043` [1A_027] **Aumento de las tasas de interés**

**JPM-B7** — 2 riesgos
  - `R-JPM-045` [1A_028] **Valuación de instrumentos financieros**
  - `R-JPM-046` [1A_028] **Disposición de instrumentos financieros**

**JPM-B8** — 2 riesgos
  - `R-JPM-063` [1A_038] **Ataque cibernético exitoso**
  - `R-JPM-068` [1A_042] **Ataques cibernéticos**

**JPM-B9** — 2 riesgos
  - `R-JPM-090` [1A_051] **Riesgos físicos del cambio climático**
  - `R-JPM-091` [1A_051] **Riesgos de transición del cambio climático**
