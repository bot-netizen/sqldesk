---
description: chronological action log per session, consolidated weekly
---
# Memory

> Chronological action log. Hooks and AI append to this file automatically.
> Old sessions are consolidated by the daemon weekly.
| 10:18 | Created plan/0.7-nav.md | — | ~2391 |
| 10:18 | Edited plan/0.8-plan.md | expanded (+32 lines) | ~457 |
| 10:19 | Edited plan/open-questions.md | expanded (+7 lines) | ~208 |
| 10:19 | Edited plan/README.md | 1→2 lines | ~61 |
| 10:19 | Edited sqldesk/handlers/queries.py | added 1 import(s) | ~66 |
| 10:19 | Edited sqldesk/handlers/queries.py | modified filter_by_kind() | ~433 |
| 10:19 | Edited sqldesk/handlers/queries.py | 3→4 lines | ~44 |
| 10:20 | Edited sqldesk/handlers/queries.py | 3→4 lines | ~48 |
| 10:20 | Edited sqldesk/handlers/queries.py | 1→2 lines | ~32 |
| 10:20 | Edited sqldesk/serializers/__init__.py | added 1 import(s) | ~50 |
| 10:20 | Edited sqldesk/serializers/__init__.py | modified streaming_data_source_ids() | ~368 |
| 10:20 | Edited sqldesk/serializers/__init__.py | expanded (+6 lines) | ~145 |
| 10:21 | Edited sqldesk/models/__init__.py | expanded (+14 lines) | ~290 |
| 10:21 | Edited sqldesk/models/__init__.py | modified is_streaming() | ~234 |
| 10:21 | Edited sqldesk/handlers/widgets.py | 24→29 lines | ~365 |
| 10:21 | Edited sqldesk/serializers/__init__.py | removed 14 lines | ~35 |
| 10:21 | Edited sqldesk/serializers/__init__.py | 7→6 lines | ~116 |
| 10:22 | Edited sqldesk/handlers/dashboards.py | modified filter_by_kind() | ~267 |
| 10:22 | Edited sqldesk/handlers/dashboards.py | removed 20 lines | ~34 |
| 10:22 | Edited sqldesk/handlers/dashboards.py | 3→4 lines | ~50 |
| 10:22 | Edited sqldesk/handlers/dashboards.py | 3→4 lines | ~51 |
| 10:22 | Edited sqldesk/handlers/dashboards.py | modified streams_for() | ~310 |
| 10:22 | Edited sqldesk/handlers/dashboards.py | streams_for() → can() | ~47 |
| 10:22 | Edited sqldesk/handlers/dashboards.py | inline fix | ~12 |
| 10:23 | Created migrations/versions/a1c7f30e95bd_dashboard_kind.py | — | ~738 |
| 10:26 | Created tests/handlers/test_kind_partition.py | — | ~671 |
| 10:26 | Created tests/handlers/test_kind_partition.py | — | ~3110 |
| 10:29 | Edited sqldesk/handlers/queries.py | modified in() | ~247 |
| 10:29 | Edited sqldesk/handlers/queries.py | 2→1 lines | ~13 |
| 10:29 | Edited tests/handlers/test_kind_partition.py | modified test_a_query_pointed_at_nothing_is_in_neither_half_and_in_no_list() | ~268 |
| 10:29 | Edited tests/handlers/test_kind_partition.py | modified test_and_a_streaming_one_when_asked_for() | ~405 |
| 10:29 | Edited tests/handlers/test_kind_partition.py | expanded (+6 lines) | ~62 |
| 10:30 | Edited tests/handlers/test_kind_partition.py | modified test_and_when_the_install_does_not_offer_streams_at_all() | ~206 |
| 10:41 | Edited client/app/pages/queries-list/QueriesList.jsx | CSS: set, STREAMING_BASE, base | ~330 |
| 10:41 | Edited client/app/pages/queries-list/QueriesList.jsx | modified QueriesList() | ~49 |
| 10:41 | Edited client/app/pages/queries-list/QueriesList.jsx | CSS: here | ~191 |
| 10:41 | Edited client/app/pages/queries-list/QueriesList.jsx | 10→14 lines | ~174 |
| 10:41 | Edited client/app/services/query.js | modified getUrl() | ~252 |
| 10:43 | Created client/app/components/dashboards/CreateDashboardDialog.jsx | — | ~1315 |
| 10:43 | Created client/app/components/dashboards/CreateDashboardDialog.less | — | ~134 |
| 10:44 | Edited client/app/pages/settings.menu.js | added 1 import(s) | ~28 |
| 10:44 | Edited client/app/pages/settings.menu.js | expanded (+22 lines) | ~298 |
| 10:44 | Edited client/app/pages/settings.menu.js | 6→10 lines | ~127 |
| 10:45 | Created client/app/pages/streams/streams.routes.jsx | — | ~981 |
| 10:45 | Edited client/app/pages/streams/streams.routes.jsx | expanded (+9 lines) | ~169 |
| 10:45 | Edited client/app/pages/streams/streams.routes.jsx | added 1 import(s) | ~44 |
| 10:51 | Created client/app/pages/queries-list/QueriesList.test.js | — | ~1226 |
| 10:55 | Created client/app/pages/dashboards/DashboardList.test.js | — | ~1284 |
| 10:56 | Created client/app/components/dashboards/CreateDashboardDialog.test.js | — | ~1071 |
| 11:09 | Created client/app/components/QuerySelector.test.js | — | ~983 |
| 11:10 | Created client/app/components/dashboards/AddWidgetDialog.test.js | — | ~543 |
<!-- session:YjU3OTQ4MTUtMDUyOC00ZDBmLWFhNzgtMDNiYzI2YTJlNjNj -->
| 2026-10-03T15:18:16.796Z | Restructured the navigation: streaming became a half of Queries and a half of Dashboards instead of a Kafka-named section of its own, the two halves never overlap, a dashboard's kind became a declared column, and three defects the old split had caused were fixed (getUrl stream-blind, QueryView had no stream support, the widget picker offered the wrong kind). | client/app/components/ApplicationArea/ApplicationLayout/DesktopNavbar.jsx,client/app/components/ApplicationArea/ApplicationLayout/MobileNavbar.jsx,client/app/pages/queries-list/QueriesList.jsx,client/app/pages/dashboards/DashboardList.jsx,client/app/pages/streams/streams.routes.jsx,client/app/pages/streams/ManageTopics.jsx,client/app/pages/settings.menu.js,client/app/services/query.js,client/app/components/QuerySelector.jsx,sqldesk/handlers/queries.py,sqldesk/handlers/dashboards.py,sqldesk/handlers/widgets.py,sqldesk/models/__init__.py,sqldesk/serializers/__init__.py,migrations/versions/a1c7f30e95bd_dashboard_kind.py,plan/0.7-nav.md | 2345 backend and 689 frontend tests pass; 17 mutations applied, 17 caught; migration a1c7f30e95bd applied on minikube; deployed as 0.7-dev48 |
| 11:43 | Created client/cypress/integration/settings/settings_tabs_spec.js | — | ~692 |
| 11:53 | Created tests/test_build_hygiene.py | — | ~824 |
| 14:40 | Created examples/kafka-demo.yaml | — | ~1112 |
| 17:23 | Created examples/mailpit.yaml | — | ~452 |
| 10:46 | Session end: 55 writes across 25 files (0.7-nav.md, 0.8-plan.md, open-questions.md, README.md, queries.py) | 56 reads | ~36000 tok |

## Session: 2026-10-18 13:10

| Time | Action | File(s) | Outcome | ~Tokens |
|------|--------|---------|---------|--------|

## Session: 2026-10-18 13:10

| Time | Action | File(s) | Outcome | ~Tokens |
|------|--------|---------|---------|--------|
| 04:55 | Created examples/values-production.yaml | — | ~1227 |
| 06:26 | Edited charts/sqldesk/templates/migrate-job.yaml | expanded (+6 lines) | ~258 |
| 06:27 | Created tests/test_chart.py | — | ~975 |
| 06:29 | Edited docs/guide/deploying.html | 4→8 lines | ~122 |
| 06:29 | Edited docs/guide/deploying.html | 1→4 lines | ~110 |
| 06:30 | Edited CHANGELOG.md | expanded (+20 lines) | ~231 |
| 06:32 | Edited examples/values-production.yaml | expanded (+13 lines) | ~348 |
| 06:32 | Edited docs/guide/deploying.html | expanded (+11 lines) | ~290 |
| 06:34 | Edited CHANGELOG.md | expanded (+10 lines) | ~226 |
| 18:42 | Created sqldesk/streams/decode.py | — | ~8674 |
| 18:45 | Created migrations/versions/d4b2a8e61f37_stream_value_formats.py | — | ~318 |
| 18:50 | Created tests/streams/test_decode.py | — | ~8659 |
| 18:53 | Created tests/streams/test_decode_streams.py | — | ~3504 |
| 19:10 | Edited docs/guide/streams.html | expanded (+41 lines) | ~836 |
| 19:24 | Edited CHANGELOG.md | expanded (+38 lines) | ~495 |
| 08:22 | Created plan/0.7.7-plan.md | — | ~3888 |
| 18:54 | Edited sqldesk/handlers/dashboards.py | 4→4 lines | ~59 |
| 18:57 | Created tests/query_runner/test_runner_faults.py | — | ~1101 |
| 05:52 | Created client/app/lib/lazyPage.js | — | ~922 |
| 05:53 | Created client/app/lib/lazyPage.test.js | — | ~1248 |
| 05:53 | Edited client/app/components/ApplicationArea/index.jsx | CSS: happens | ~377 |
| 05:53 | Edited client/app/components/ApplicationArea/index.jsx | added 2 condition(s) | ~379 |
| 05:53 | Edited client/app/components/ApplicationArea/index.jsx | 5→1 lines | ~22 |
| 05:54 | Created client/app/components/ApplicationArea/index.test.js | — | ~806 |
| 05:58 | Created client/app/lib/hooks/usePolledData.js | — | ~1043 |
| 05:58 | Created client/app/lib/hooks/usePolledData.test.js | — | ~1526 |
| 05:59 | Created client/app/components/admin/StaleNotice.jsx | — | ~333 |
| 06:06 | Edited sqldesk/query_runner/__init__.py | expanded (+50 lines) | ~582 |
| 06:07 | Edited sqldesk/query_runner/__init__.py | 3→7 lines | ~74 |
| 06:07 | Edited sqldesk/query_runner/__init__.py | modified query_language_for() | ~176 |
| 06:08 | Edited sqldesk/mcp/__init__.py | expanded (+7 lines) | ~79 |
| 06:09 | Edited sqldesk/mcp/__init__.py | removed 36 lines | ~22 |
| 06:09 | Edited sqldesk/mcp/__init__.py | 5→7 lines | ~84 |
| 06:09 | Edited sqldesk/mcp/__init__.py | modified _language() | ~571 |
| 06:09 | Edited sqldesk/mcp/__init__.py | expanded (+7 lines) | ~124 |
| 06:09 | Edited sqldesk/mcp/__init__.py | expanded (+7 lines) | ~194 |
| 06:10 | Created tests/query_runner/test_query_language.py | — | ~1493 |
| 06:10 | Edited sqldesk/mcp/__init__.py | expanded (+8 lines) | ~173 |
| 06:10 | Edited sqldesk/mcp/__init__.py | modified _language() | ~40 |
| 06:11 | Edited tests/query_runner/test_query_language.py | test_python_says_so() → test_python_says_so_even_where_the_runner_is_switched_off() | ~129 |
| 06:11 | Edited sqldesk/mcp/__init__.py | modified _language() | ~62 |
| 06:11 | Edited sqldesk/mcp/__init__.py | expanded (+8 lines) | ~185 |
| 06:17 | Created tests/handlers/test_mcp_languages.py | — | ~735 |
| 06:21 | Edited sqldesk/query_runner/prometheus.py | added 1 import(s) | ~60 |
| 06:21 | Edited sqldesk/query_runner/prometheus.py | modified split_query_body() | ~451 |
| 06:21 | Edited sqldesk/query_runner/prometheus.py | modified keys() | ~134 |
| 06:22 | Edited sqldesk/query_runner/prometheus.py | parse_qs() → split_query_body() | ~107 |
| 06:22 | Edited tests/query_runner/test_prometheus.py | modified test_a_plus_is_an_operator_not_a_space() | ~586 |
| 06:22 | Edited tests/query_runner/test_prometheus.py | 6→7 lines | ~40 |
| 06:24 | Edited sqldesk/query_runner/prometheus.py | modified epoch() | ~493 |
| 06:24 | Edited sqldesk/query_runner/prometheus.py | modified _get_datetime_now() | ~40 |
| 06:24 | Edited sqldesk/query_runner/prometheus.py | added error handling | ~310 |
| 06:25 | Edited tests/query_runner/test_prometheus.py | modified test_now_is_now() | ~986 |
| 06:25 | Edited tests/query_runner/test_prometheus.py | modified test_a_relative_range_reaches_the_api_as_two_timestamps() | ~84 |
| 06:27 | Edited sqldesk/query_runner/prometheus.py | added error handling | ~1377 |
| 06:27 | Edited sqldesk/query_runner/prometheus.py | modified sample_time() | ~108 |
| 06:27 | Edited sqldesk/query_runner/prometheus.py | 6→2 lines | ~20 |
| 06:27 | Edited sqldesk/query_runner/prometheus.py | 22→17 lines | ~221 |
| 06:28 | Edited tests/query_runner/test_prometheus.py | modified answer() | ~1596 |
| 06:30 | Edited sqldesk/query_runner/prometheus.py | added error handling | ~291 |
| 06:30 | Edited sqldesk/query_runner/prometheus.py | raise_for_status() → api_error() | ~64 |
| 06:30 | Edited sqldesk/query_runner/prometheus.py | 4→6 lines | ~114 |
| 06:30 | Edited sqldesk/query_runner/prometheus.py | 4→5 lines | ~60 |
| 06:30 | Edited sqldesk/query_runner/prometheus.py | modified test_connection() | ~477 |
| 06:31 | Edited tests/query_runner/test_prometheus.py | modified test_test_connection_asks_what_the_tenant_holds() | ~502 |
| 06:31 | Edited tests/query_runner/test_prometheus.py | modified refusal() | ~866 |
| 06:32 | Edited sqldesk/query_runner/prometheus.py | modified configuration_schema() | ~476 |
| 06:33 | Edited sqldesk/query_runner/prometheus.py | expanded (+9 lines) | ~144 |
| 06:33 | Edited sqldesk/query_runner/prometheus.py | 4→5 lines | ~36 |
| 06:33 | Edited sqldesk/query_runner/prometheus.py | added error handling | ~156 |
| 06:33 | Edited sqldesk/query_runner/prometheus.py | expanded (+6 lines) | ~257 |
| 06:33 | Edited tests/query_runner/test_prometheus.py | modified test_the_default_applies_when_nobody_set_one() | ~913 |
| 06:35 | Edited sqldesk/query_runner/prometheus.py | expanded (+11 lines) | ~356 |
| 11:30 | Created Dockerfile | — | ~3058 |
| 11:30 | Edited Dockerfile | expanded (+32 lines) | ~395 |
| 11:30 | Edited Dockerfile | removed 24 lines | ~36 |
| 11:30 | Edited webpack.config.js | 1→6 lines | ~128 |
| 11:32 | Edited Dockerfile | 3→7 lines | ~65 |
| 11:32 | Edited Dockerfile | 2→2 lines | ~31 |
| 11:33 | Created tests/test_discovery_documents.py | — | ~1079 |
| 11:33 | Edited tests/test_discovery_documents.py | "." → ".json" | ~20 |
| 11:44 | Edited docs/guide/deploying.html | expanded (+9 lines) | ~250 |
| 11:44 | Edited docs/guide/deploying.html | 2→2 lines | ~58 |
| 11:50 | Edited Dockerfile | 5→6 lines | ~108 |
| 11:50 | Edited Dockerfile | expanded (+9 lines) | ~199 |
| 11:52 | Edited Dockerfile | removed 9 lines | ~7 |
| 11:52 | Edited Dockerfile | 3→3 lines | ~47 |
| 11:52 | Edited Dockerfile | removed 26 lines | ~17 |
| 11:52 | Edited webpack.config.js | removed 6 lines | ~21 |
| 06:16 | Edited Dockerfile | expanded (+105 lines) | ~1446 |
| 07:52 | Edited migrations/env.py | expanded (+6 lines) | ~141 |
| 07:52 | Edited tests/test_migrations.py | added 1 import(s) | ~13 |
| 07:52 | Edited tests/test_migrations.py | modified test_compiling_one_leaves_the_rest_of_the_process_able_to_log() | ~298 |
| 07:55 | Edited plan/0.7.7-plan.md | expanded (+6 lines) | ~223 |
| 07:55 | Edited plan/0.7.7-plan.md | 2→2 lines | ~33 |
| 07:57 | Edited tests/factories.py | modified _get_kwargs() | ~200 |
| 07:57 | Edited tests/factories.py | 1→4 lines | ~46 |
| 07:57 | Edited tests/factories.py | added 1 import(s) | ~21 |
| 07:57 | Created tests/test_factories.py | — | ~540 |
| 07:58 | Created tests/test_factories.py | — | ~646 |
| 07:58 | Edited tests/factories.py | 2→1 lines | ~34 |
| 08:08 | Edited sqldesk/handlers/queries.py | 2→4 lines | ~87 |
| 08:09 | Edited tests/handlers/test_queries.py | modified test_and_the_new_key_comes_back_in_the_answer() | ~385 |
| 08:11 | Edited sqldesk/handlers/widgets.py | 1→4 lines | ~85 |
| 08:11 | Edited tests/handlers/test_widgets.py | modified test_create_text_widget_without_mentioning_a_visualization_at_all() | ~263 |
| 08:22 | Created plan/0.7.7-verification.md | — | ~2144 |
| 08:22 | Edited plan/README.md | 1→3 lines | ~99 |
| 08:27 | Edited plan/local-dev.md | expanded (+21 lines) | ~258 |
| 08:30 | Edited docs/guide/streams.html | expanded (+33 lines) | ~641 |
| 09:19 | Edited docs/tools/chrome.py | 12→10 lines | ~94 |
| 09:20 | Edited docs/tools/chrome.py | modified startswith() | ~125 |
| 09:29 | Edited docs/guide/queries.html | expanded (+18 lines) | ~383 |
| 09:30 | Edited docs/guide/alerts.html | expanded (+18 lines) | ~335 |
| 09:58 | Created docs/_mark-options.html | — | ~2902 |
| 13:03 | Created plan/agent-context.md | — | ~1778 |
| 13:07 | Edited sqldesk/mcp/__init__.py | modified _text() | ~292 |
| 13:09 | Edited sqldesk/mcp/__init__.py | modified _charts_by_query() | ~98 |
| 13:10 | Edited sqldesk/mcp/__init__.py | 8→9 lines | ~77 |
| 13:10 | Edited sqldesk/mcp/__init__.py | modified _charts_by_query() | ~684 |
| 13:10 | Edited sqldesk/mcp/__init__.py | expanded (+10 lines) | ~124 |
| 13:11 | Edited sqldesk/mcp/__init__.py | removed 14 lines | ~15 |
| 13:11 | Edited sqldesk/mcp/__init__.py | modified _options_for_described() | ~236 |
| 13:39 | Edited docs/index.html | added 1 condition(s) | ~265 |
| 13:41 | Edited sqldesk/mcp/__init__.py | 6→11 lines | ~170 |
| 16:08 | Created blog/an-agent-that-knows-who-wrote-it.md | — | ~3916 |
| 16:46 | Created docs/_card.html | — | ~748 |
| 19:06 | Created client/app/lib/browserNoise.js | — | ~494 |
| 19:06 | Created client/app/lib/browserNoise.test.js | — | ~406 |
| 19:06 | Edited client/app/components/ApplicationArea/index.jsx | added 1 import(s) | ~30 |
| 19:06 | Edited client/app/components/ApplicationArea/index.jsx | added 1 condition(s) | ~130 |
| 19:06 | Edited client/app/components/ApplicationArea/index.test.js | expanded (+11 lines) | ~150 |
| 19:09 | Created client/app/lib/logoAssets.js | — | ~630 |
| 19:09 | Edited client/app/components/TypeLogo.tsx | added 1 import(s) | ~44 |
| 19:09 | Edited client/app/components/TypeLogo.tsx | 3→8 lines | ~161 |
| 19:09 | Edited client/app/components/TypeLogo.tsx | 3→3 lines | ~36 |
| 19:09 | Created client/app/lib/logoAssets.test.js | — | ~390 |
| 19:09 | Edited client/app/components/TypeLogo.test.js | 4→9 lines | ~110 |
| 19:09 | Edited client/app/components/TypeLogo.test.js | expanded (+12 lines) | ~170 |
| 19:11 | Edited sqldesk/settings/__init__.py | expanded (+14 lines) | ~276 |
| 19:12 | Edited sqldesk/settings/__init__.py | expanded (+6 lines) | ~269 |
| 19:12 | Edited tests/tasks/test_schedule.py | added 1 import(s) | ~110 |
| 19:12 | Edited tests/tasks/test_schedule.py | modified _interval_of() | ~434 |
| 19:14 | Edited tests/tasks/test_schedule.py | modified test_the_default_is_not_a_few_minutes() | ~140 |
| 19:14 | Edited tests/tasks/test_schedule.py | 2→2 lines | ~26 |
| 19:17 | Edited client/app/components/items-list/components/ListPageControls.jsx | 3→3 lines | ~48 |
| 19:17 | Edited client/app/components/items-list/components/ListPageControls.jsx | FilterControl() → SearchControl() | ~253 |
| 19:17 | Edited client/app/components/items-list/components/ListPageControls.jsx | reduced (-14 lines) | ~196 |
| 19:17 | Edited client/app/components/items-list/components/ListPageControls.less | expanded (+10 lines) | ~206 |
| 19:17 | Edited client/app/components/items-list/components/ListPageControls.test.js | 5→5 lines | ~83 |
| 19:18 | Edited client/app/components/items-list/components/ListPageControls.test.js | 23→27 lines | ~300 |
| 19:18 | Edited client/app/components/items-list/components/ListPageControls.test.js | modified type() | ~83 |
| 19:18 | Edited client/app/components/items-list/components/ListPageControls.test.js | reduced (-13 lines) | ~239 |
| 19:21 | Edited client/app/components/items-list/classes/ItemsFetcher.js | modified constructor() | ~670 |
| 19:21 | Edited client/app/components/items-list/classes/ItemsFetcher.js | modified toLowerCase() | ~175 |
| 19:21 | Edited client/app/components/items-list/classes/ItemsSource.js | modified constructor() | ~169 |
| 19:21 | Edited client/app/pages/alerts/AlertsList.jsx | expanded (+6 lines) | ~163 |
| 19:21 | Edited client/app/pages/alerts/AlertsList.jsx | added 1 import(s) | ~72 |
| 19:22 | Edited client/app/pages/alerts/AlertsList.jsx | CSS: s | ~201 |
| 19:22 | Created client/app/components/items-list/classes/ItemsFetcher.test.js | — | ~1552 |
| 19:40 | Edited viz-lib/src/visualizations/chart/getOptions.ts | expanded (+9 lines) | ~203 |
| 19:40 | Edited viz-lib/src/visualizations/chart/echarts/buildOption.ts | added 3 condition(s) | ~382 |
| 19:40 | Edited viz-lib/src/visualizations/chart/echarts/buildOption.ts | added 1 condition(s) | ~295 |
| 19:40 | Created viz-lib/src/visualizations/chart/Editor/ThresholdColorSettings.tsx | — | ~996 |
| 19:40 | Edited viz-lib/src/visualizations/chart/Editor/DefaultColorsSettings.tsx | added 1 import(s) | ~42 |
| 19:41 | Edited viz-lib/src/visualizations/chart/Editor/DefaultColorsSettings.tsx | CSS: only | ~110 |
| 19:41 | Created viz-lib/src/visualizations/chart/echarts/buildOption.threshold.test.ts | — | ~1408 |
| 19:41 | Edited viz-lib/src/visualizations/chart/echarts/buildOption.threshold.test.ts | expanded (+10 lines) | ~192 |
| 19:43 | Edited viz-lib/src/visualizations/chart/echarts/buildOption.threshold.test.ts | expanded (+26 lines) | ~502 |
| 19:45 | Edited viz-lib/src/visualizations/chart/Editor/ThresholdColorSettings.tsx | 4→4 lines | ~69 |
| 19:45 | Edited viz-lib/src/visualizations/chart/Editor/ThresholdColorSettings.tsx | expanded (+6 lines) | ~359 |
| 19:45 | Edited viz-lib/src/visualizations/chart/Editor/ThresholdColorSettings.tsx | expanded (+12 lines) | ~639 |
| 19:45 | Edited viz-lib/src/visualizations/chart/Editor/ThresholdColorSettings.tsx | CSS: EditorPropTypes, options, onOptionsChange | ~80 |
| 19:46 | Created viz-lib/src/visualizations/chart/Editor/ThresholdColorSettings.tsx | — | ~1130 |
| 19:46 | Edited viz-lib/src/visualizations/chart/Editor/ThresholdColorSettings.tsx | CSS: FIXME, FIXME, FIXME | ~156 |
| 19:48 | Edited viz-lib/src/visualizations/table/cellFormat.ts | expanded (+7 lines) | ~171 |
| 19:49 | Edited viz-lib/src/visualizations/table/cellFormat.ts | added 3 condition(s) | ~523 |
| 19:49 | Edited viz-lib/src/visualizations/table/utils.tsx | CSS: left, background, dataBarNegativeColor | ~254 |
| 19:49 | Edited viz-lib/src/visualizations/table/utils.tsx | expanded (+9 lines) | ~59 |
| 19:49 | Edited viz-lib/src/visualizations/table/renderer.less | expanded (+19 lines) | ~255 |
| 19:49 | Edited viz-lib/src/visualizations/table/Editor/CellFormatSection.tsx | expanded (+20 lines) | ~299 |
| 19:49 | Edited viz-lib/src/visualizations/table/Editor/CellFormatSection.tsx | 31→32 lines | ~328 |
| 19:50 | Edited viz-lib/src/visualizations/table/cellFormat.test.tsx | expanded (+54 lines) | ~842 |
| 19:51 | Edited viz-lib/src/visualizations/table/cellFormat.test.tsx | expanded (+34 lines) | ~484 |
| 19:52 | Edited viz-lib/src/visualizations/table/utils.tsx | expanded (+9 lines) | ~59 |
| 19:52 | Edited viz-lib/src/visualizations/table/utils.tsx | CSS: left, background, dataBarNegativeColor | ~254 |
| 19:55 | Edited sqldesk/mcp/__init__.py | expanded (+66 lines) | ~970 |
| 19:56 | Edited sqldesk/mcp/__init__.py | modified may_write_dashboards() | ~2540 |
| 19:56 | Edited sqldesk/mcp/__init__.py | 4→5 lines | ~56 |
| 19:57 | Edited sqldesk/mcp/__init__.py | modified may_write_queries() | ~197 |
| 19:57 | Edited sqldesk/mcp/__init__.py | 3→5 lines | ~61 |
| 19:57 | Edited sqldesk/mcp/__init__.py | modified may_write_queries() | ~66 |
| 19:57 | Edited sqldesk/mcp/__init__.py | expanded (+7 lines) | ~42 |
| 19:58 | Edited tests/handlers/test_mcp.py | modified setUp() | ~2061 |
| 20:01 | Edited sqldesk/mcp/__init__.py | 5→1 lines | ~22 |
| 20:05 | Edited sqldesk/mcp/__init__.py | removed 14 lines | ~26 |
| 20:05 | Edited sqldesk/mcp/__init__.py | modified _offered_tools() | ~241 |
| 20:06 | Edited docs/guide/deploying.html | expanded (+48 lines) | ~801 |
| 20:06 | Edited docs/guide/mcp.html | expanded (+17 lines) | ~519 |
| 20:06 | Edited README.md | 2→2 lines | ~55 |
| 20:07 | Edited docs/index.html | 2→3 lines | ~80 |
| 20:08 | Created plan/0.7.8-plan.md | — | ~1316 |
| 20:09 | Edited CHANGELOG.md | expanded (+79 lines) | ~1044 |
| 20:28 | Edited tests/models/test_data_sources.py | added 2 import(s) | ~67 |
| 20:28 | Edited tests/models/test_data_sources.py | modified test_expires_schema() | ~199 |
| 20:33 | Edited docs/guide/visualizations.html | expanded (+29 lines) | ~515 |
| 20:38 | Edited sqldesk/mcp/__init__.py | 4→7 lines | ~110 |
| 20:38 | Edited sqldesk/mcp/__init__.py | 3→4 lines | ~78 |
| 20:38 | Edited tests/handlers/test_mcp.py | modified test_a_pie_always_gets_a_legend() | ~113 |
| 21:20 | Edited sqldesk/handlers/authentication.py | added 1 import(s) | ~73 |
| 21:20 | Edited sqldesk/handlers/authentication.py | modified _org_setting() | ~331 |
| 21:20 | Edited sqldesk/handlers/authentication.py | 1→4 lines | ~71 |
| 21:20 | Edited sqldesk/handlers/authentication.py | modified config() | ~156 |
| 21:21 | Edited sqldesk/handlers/authentication.py | modified base_href() | ~181 |
| 21:22 | Edited sqldesk/handlers/authentication.py | modified base_href() | ~203 |
| 21:24 | Edited CHANGELOG.md | expanded (+8 lines) | ~187 |
| 21:24 | Edited plan/0.7.8-plan.md | expanded (+19 lines) | ~321 |
| 21:32 | Edited docs/releases.html | expanded (+11 lines) | ~381 |
| 08:06 | Edited sqldesk/mcp/__init__.py | expanded (+6 lines) | ~148 |
| 08:06 | Edited sqldesk/mcp/__init__.py | 4→9 lines | ~171 |
| 08:07 | Edited tests/handlers/test_mcp.py | modified test_every_row_the_query_was_allowed_to_return_is_returned() | ~806 |
| 08:24 | Edited sqldesk/models/__init__.py | modified evaluate() | ~203 |
| 08:24 | Edited sqldesk/models/__init__.py | 6→7 lines | ~61 |
| 08:25 | Edited sqldesk/models/__init__.py | modified __str__() | ~558 |
| 08:25 | Edited sqldesk/tasks/alerts.py | modified should_notify() | ~444 |
| 08:25 | Created migrations/versions/f3a71c20e9d5_alert_fires.py | — | ~498 |
| 08:30 | Edited sqldesk/models/__init__.py | modified fire_counts_since() | ~449 |
| 08:30 | Edited sqldesk/serializers/__init__.py | modified serialize_alert_fire() | ~361 |
| 08:30 | Edited sqldesk/handlers/alerts.py | modified get() | ~178 |
| 08:31 | Edited sqldesk/models/__init__.py | modified fire_counts() | ~479 |
| 08:31 | Edited sqldesk/handlers/alerts.py | 4→4 lines | ~78 |
| 08:31 | Edited sqldesk/handlers/alerts.py | modified get() | ~180 |
| 08:56 | Edited client/app/pages/alerts/AlertsList.jsx | CSS: quiet, className | ~325 |
| 08:56 | Created client/app/pages/alert/components/AlertHistory.jsx | — | ~856 |
| 08:57 | Created client/app/pages/alert/components/AlertHistory.test.js | — | ~937 |
| 08:59 | Edited sqldesk/models/__init__.py | modified render_template() | ~238 |
| 08:59 | Edited sqldesk/destinations/slack.py | 11→13 lines | ~189 |
| 09:00 | Edited sqldesk/models/__init__.py | expanded (+6 lines) | ~165 |
| 09:02 | Edited docs/guide/alerts.html | expanded (+63 lines) | ~1231 |
| 09:02 | Edited client/app/components/HelpTrigger.jsx | CSS: ALERT_SLACK_FORMATTING | ~55 |
| 09:02 | Edited client/app/pages/alert/components/NotificationTemplate.jsx | CSS: wrong | ~183 |
| 09:17 | Edited CHANGELOG.md | expanded (+55 lines) | ~698 |
| 09:20 | Created client/app/lib/initialsTile.js | — | ~494 |
| 09:20 | Created client/app/components/UserAvatar.jsx | — | ~724 |
| 09:20 | Created client/app/components/UserAvatar.less | — | ~138 |
| 09:20 | Edited sqldesk/models/users.py | modified profile_image_url() | ~297 |
| 09:22 | Created client/app/components/UserAvatar.test.js | — | ~1036 |
| 09:35 | Created plan/0.7.10-plan.md | — | ~980 |
| 06:59 | Created viz-lib/src/visualizations/chart/lineDash.ts | — | ~615 |
| 07:01 | Created viz-lib/src/visualizations/chart/echarts/buildOption.lineDash.test.ts | — | ~1406 |
| 09:16 | Created viz-lib/src/visualizations/chart/panels.ts | — | ~1626 |
| 09:16 | Edited viz-lib/src/visualizations/chart/echarts/buildOption.ts | added 1 import(s) | ~59 |
| 09:17 | Edited viz-lib/src/visualizations/chart/echarts/buildOption.ts | modified buildCartesianSeries() | ~44 |
| 09:17 | Edited viz-lib/src/visualizations/chart/echarts/buildOption.ts | expanded (+9 lines) | ~268 |
| 09:17 | Edited viz-lib/src/visualizations/chart/echarts/buildOption.ts | modified buildPieSeries() | ~212 |
| 09:18 | Edited viz-lib/src/visualizations/chart/echarts/buildOption.ts | expanded (+11 lines) | ~422 |
| 09:18 | Edited viz-lib/src/visualizations/chart/echarts/buildOption.ts | added 2 condition(s) | ~1001 |
| 09:18 | Edited viz-lib/src/visualizations/chart/echarts/buildOption.ts | inline fix | ~28 |
| 09:18 | Edited viz-lib/src/visualizations/chart/echarts/buildOption.ts | 8→13 lines | ~160 |
| 09:18 | Edited viz-lib/src/visualizations/chart/getOptions.ts | expanded (+6 lines) | ~94 |
| 09:20 | Created viz-lib/src/visualizations/chart/echarts/buildOption.panels.test.ts | — | ~4650 |
| 09:21 | Created viz-lib/src/visualizations/chart/Editor/PanelSettings.tsx | — | ~1146 |
| 09:21 | Edited viz-lib/src/visualizations/chart/Editor/YAxisSettings.tsx | CSS: are | ~183 |
| 09:22 | Edited viz-lib/src/visualizations/chart/Editor/SeriesSettings.tsx | added 1 condition(s) | ~294 |
| 09:22 | Edited viz-lib/src/visualizations/chart/Editor/SeriesSettings.tsx | inline fix | ~21 |
| 09:22 | Edited viz-lib/src/visualizations/chart/Editor/SeriesSettings.tsx | added 2 import(s) | ~58 |
| 09:22 | Edited viz-lib/src/visualizations/chart/Editor/PanelSettings.tsx | 3→2 lines | ~40 |
| 09:23 | Created viz-lib/src/visualizations/chart/Editor/PanelSettings.test.tsx | — | ~1894 |
| 09:23 | Edited viz-lib/src/visualizations/chart/Editor/PanelSettings.test.tsx | CSS: target, value | ~41 |
| 09:24 | Edited sqldesk/mcp/__init__.py | 12→17 lines | ~292 |
| 09:25 | Edited sqldesk/mcp/__init__.py | expanded (+7 lines) | ~158 |
| 09:25 | Edited sqldesk/mcp/__init__.py | expanded (+29 lines) | ~768 |
| 09:29 | Edited tests/handlers/test_mcp.py | modified offered_types() | ~110 |
| 09:39 | Edited viz-lib/src/visualizations/chart/echarts/buildOption.ts | 11→12 lines | ~196 |
| 09:39 | Edited viz-lib/src/visualizations/chart/echarts/buildOption.ts | expanded (+27 lines) | ~322 |
| 10:55 | Created viz-lib/src/visualizations/chart/panels.ts | — | ~1438 |
| 10:55 | Edited viz-lib/src/visualizations/chart/echarts/buildOption.ts | inline fix | ~24 |
| 10:55 | Edited viz-lib/src/visualizations/chart/echarts/buildOption.ts | 4→3 lines | ~28 |
| 10:55 | Edited viz-lib/src/visualizations/chart/echarts/buildOption.ts | 5→5 lines | ~37 |
| 10:55 | Edited viz-lib/src/visualizations/chart/echarts/buildOption.ts | removed 28 lines | ~7 |
| 10:55 | Edited viz-lib/src/visualizations/chart/echarts/buildOption.ts | 10→10 lines | ~164 |
| 10:55 | Edited viz-lib/src/visualizations/chart/getOptions.ts | 6→5 lines | ~69 |
| 10:56 | Created viz-lib/src/visualizations/chart/Editor/PanelSettings.tsx | — | ~615 |
| 10:57 | Edited viz-lib/src/visualizations/chart/Editor/PanelSettings.test.tsx | 6→8 lines | ~126 |
| 11:00 | Edited sqldesk/mcp/__init__.py | modified _chart_columns() | ~555 |
| 11:00 | Edited sqldesk/mcp/__init__.py | removed 34 lines | ~43 |
| 11:15 | Edited sqldesk/handlers/widgets.py | modified clean_tabs() | ~728 |
| 11:15 | Edited sqldesk/handlers/widgets.py | 7→8 lines | ~82 |
| 11:15 | Edited sqldesk/handlers/widgets.py | 3→3 lines | ~45 |
| 11:15 | Edited sqldesk/serializers/__init__.py | modified _serialize_widget_tabs() | ~377 |
| 11:19 | Edited client/app/services/widget.js | modified if() | ~107 |
| 11:19 | Edited client/app/services/widget.js | added 1 condition(s) | ~220 |
| 11:20 | Edited client/app/services/widget.js | 4→5 lines | ~14 |
| 11:20 | Edited client/app/components/dashboards/dashboard-widget/VisualizationWidget.jsx | CSS: saved, activeTabId | ~126 |
| 11:20 | Edited client/app/components/dashboards/dashboard-widget/VisualizationWidget.jsx | CSS: active, activeTabId, id | ~490 |
| 11:20 | Edited client/app/components/dashboards/dashboard-widget/VisualizationWidget.jsx | 12→13 lines | ~121 |
| 11:20 | Edited client/app/components/dashboards/dashboard-widget/VisualizationWidget.jsx | inline fix | ~18 |
| 11:21 | Created client/app/components/dashboards/ChooseWidgetTabsDialog.jsx | — | ~1202 |
| 11:22 | Created client/app/components/dashboards/dashboard-widget/VisualizationWidget.tabs.test.js | — | ~1594 |
| 11:24 | Edited client/app/components/dashboards/dashboard-widget/VisualizationWidget.jsx | expanded (+14 lines) | ~332 |
| 11:41 | Created viz-lib/src/visualizations/chart/rollup.ts | — | ~1167 |
| 11:41 | Edited viz-lib/src/visualizations/chart/rollup.ts | modified startRollup() | ~112 |
| 11:41 | Edited viz-lib/src/visualizations/chart/rollup.ts | 10→10 lines | ~90 |
| 11:41 | Edited viz-lib/src/visualizations/chart/rollup.ts | modified if() | ~126 |
| 11:42 | Edited viz-lib/src/visualizations/chart/echarts/buildOption.ts | modified aggregate() | ~536 |
| 11:43 | Created viz-lib/src/visualizations/chart/echarts/buildOption.rollup.test.ts | — | ~1698 |
| 11:44 | Created viz-lib/src/visualizations/chart/Editor/RollupSetting.test.tsx | — | ~790 |
| 13:47 | Created sqldesk/pools.py | — | ~2550 |
| 13:49 | Created tests/test_pools.py | — | ~3223 |
| 14:04 | Created sqldesk/notebooks.py | — | ~1490 |
| 14:54 | Created sqldesk/alerting.py | — | ~1401 |
| 14:54 | Created sqldesk/destinations/slack.py | — | ~1580 |
| 06:37 | Created sqldesk/notebooks/store.py | — | ~3736 |
| 06:38 | Created tests/notebooks/test_store.py | — | ~3325 |
| 09:01 | Created sqldesk/notebooks/run.py | — | ~2509 |
| 09:02 | Created tests/notebooks/test_run.py | — | ~3637 |
| 09:29 | Created executor/runner.py | — | ~2960 |
| 09:30 | Created executor/service.py | — | ~4058 |
| 09:30 | Created Dockerfile.executor | — | ~644 |
| 09:31 | Created tests/test_executor.py | — | ~3898 |
| 09:46 | Created sqldesk/notebooks/interpreter.py | — | ~2794 |
| 09:49 | Created tests/notebooks/test_python_cells.py | — | ~5839 |
| 10:30 | Created sqldesk/tasks/notebooks.py | — | ~901 |
| 10:31 | Created sqldesk/handlers/notebooks.py | — | ~4498 |
| 10:33 | Created tests/handlers/test_notebooks.py | — | ~4567 |
| 10:34 | Created tests/tasks/test_notebook_cells.py | — | ~1710 |
| 10:40 | Created client/app/services/notebook.js | — | ~462 |
| 10:41 | Created client/app/pages/notebooks/NotebookCell.jsx | — | ~2886 |
| 10:42 | Created client/app/pages/notebooks/Notebook.jsx | — | ~2337 |
| 10:43 | Created client/app/pages/notebooks/NotebookList.jsx | — | ~1706 |
| 10:43 | Created client/app/pages/notebooks/notebook.less | — | ~872 |
| 10:45 | Created client/app/pages/notebooks/NotebookCell.test.js | — | ~1778 |
| 10:47 | Created client/app/pages/notebooks/Notebook.test.js | — | ~1074 |
| 11:16 | Created client/app/pages/notebooks/CellVisualizationDialog.jsx | — | ~1459 |
| 11:31 | Created executor/spark.py | — | ~1307 |
| 11:32 | Created tests/test_executor_spark.py | — | ~1845 |
| 11:35 | Created docs/guide/notebooks.html | — | ~2382 |
| 12:07 | Created client/app/pages/dashboards/hooks/useRunningStreams.js | — | ~1372 |
| 12:07 | Created client/app/pages/dashboards/components/StreamMarker.jsx | — | ~1214 |
| 12:07 | Created client/app/pages/dashboards/components/StreamMarker.less | — | ~661 |
| 12:10 | Created client/app/pages/dashboards/components/StreamMarker.test.js | — | ~1741 |
| 12:14 | Created sqldesk/metrics/prometheus.py | — | ~2448 |
| 12:15 | Created tests/test_metrics_endpoint.py | — | ~1607 |
| 12:37 | Created charts/sqldesk/templates/executor.yaml | — | ~1598 |
| 13:02 | Created client/app/pages/admin/Audit.jsx | — | ~1677 |
| 13:04 | Created tests/test_audit.py | — | ~2305 |
| 13:14 | Created client/app/pages/admin/Audit.test.js | — | ~670 |
| 13:24 | Created sqldesk/mcp/layout.py | — | ~926 |
| 13:25 | Created tests/mcp/test_layout.py | — | ~1606 |
| 13:30 | Created viz-lib/src/visualizations/chart/echarts/buildOption.axisRange.test.ts | — | ~1222 |
| 13:44 | Created tests/handlers/test_permanent_delete.py | — | ~2260 |
| 13:49 | Created client/app/components/items-list/components/ListItemActions.test.js | — | ~1219 |
| 15:59 | Created migrations/versions/4b9e2d81c705_notebook_run_printed.py | — | ~198 |
| 07:10 | Created plan/0.8.1-plan.md | — | ~1383 |
| 07:11 | Created migrations/versions/5c1f7a92b4d8_notebook_cell_title.py | — | ~204 |
| 07:12 | Edited client/app/pages/notebooks/NotebookCell.jsx | CSS: reason, options | ~216 |
| 07:12 | Edited client/app/pages/notebooks/NotebookCell.jsx | CSS: collapsed | ~254 |
| 07:12 | Edited client/app/pages/notebooks/NotebookCell.jsx | CSS: point, hideCode, hideOutput | ~356 |
| 07:12 | Edited client/app/pages/notebooks/NotebookCell.jsx | CSS: it | ~161 |
| 07:12 | Edited client/app/pages/notebooks/NotebookCell.jsx | inline fix | ~13 |
| 07:12 | Edited client/app/pages/notebooks/NotebookCell.jsx | inline fix | ~12 |
| 07:12 | Edited client/app/pages/notebooks/NotebookCell.jsx | 14→18 lines | ~198 |
| 07:12 | Edited client/app/pages/notebooks/NotebookCell.jsx | CSS: dialog, cell, onChange | ~740 |
| 07:13 | Edited client/app/pages/notebooks/Notebook.jsx | added 2 condition(s) | ~635 |
| 07:13 | Edited client/app/pages/notebooks/Notebook.jsx | added 1 import(s) | ~50 |
| 07:13 | Edited client/app/pages/notebooks/Notebook.jsx | 3→4 lines | ~67 |
| 07:13 | Edited client/app/pages/notebooks/Notebook.jsx | CSS: cell, dataSources, one | ~355 |
| 07:18 | Edited client/app/pages/notebooks/Notebook.jsx | CSS: id, message | ~252 |
| 07:18 | Edited client/app/pages/notebooks/Notebook.jsx | expanded (+7 lines) | ~134 |
| 07:18 | Edited client/app/pages/notebooks/Notebook.jsx | added 1 import(s) | ~44 |
| 07:18 | Edited client/app/pages/notebooks/Notebook.jsx | CSS: docs, steps, cell | ~410 |
| 08:15 | Created migrations/versions/6d2a8e34f71b_notebook_schedule.py | — | ~339 |
| 08:45 | Created client/app/pages/notebooks/NotebookScheduleDialog.jsx | — | ~1039 |
| 14:52 | Created client/app/pages/notebooks/EditableTitle.jsx | — | ~730 |
| 14:53 | Created client/app/pages/notebooks/ShareNotebookButton.jsx | — | ~1541 |
| 15:14 | Created client/app/pages/notebooks/NotebookHelpDialog.jsx | — | ~1235 |
| 10:40 | Created client/app/pages/notebooks/ShareNotebookButton.test.js | — | ~1065 |
| 11:46 | Created client/app/pages/dashboards/export/tiles.test.js | — | ~899 |
| 12:10 | Created client/app/components/BetaBadge.jsx | — | ~382 |
| 12:10 | Created client/app/components/BetaBadge.less | — | ~170 |
| 12:11 | Created client/app/components/BetaBadge.test.js | — | ~452 |
| 12:15 | Created blog/the-work-a-query-cannot-hold.md | — | ~2958 |
| 12:29 | Created client/app/pages/notebooks/popup.js | — | ~297 |
| 18:18 | Created sqldesk/demo/data.py | — | ~1677 |
| 18:19 | Created sqldesk/demo/content.py | — | ~3409 |
| 18:20 | Created sqldesk/demo/__init__.py | — | ~2327 |
| 18:20 | Created sqldesk/cli/demo.py | — | ~1280 |
| 18:21 | Created tests/test_demo.py | — | ~2551 |
| 18:41 | Created client/app/pages/dashboards/PublicDashboardPage.branding.test.js | — | ~383 |
| 18:50 | Created client/app/pages/data-sources/DataSourcesList.test.js | — | ~398 |
| 19:46 | Edited sqldesk/cli/users.py | added error handling | ~328 |
| 19:46 | Edited sqldesk/cli/users.py | modified _still_owns() | ~574 |
| 19:47 | Edited tests/test_cli.py | modified test_delete_bad() | ~660 |
| 19:47 | Edited tests/test_cli.py | modified test_the_reason_matches_the_longest_table_name() | ~312 |
| 19:48 | Edited tests/test_cli.py | expanded (+10 lines) | ~257 |
| 19:51 | Edited plan/local-dev.md | expanded (+12 lines) | ~218 |
| 19:51 | Edited plan/local-dev.md | expanded (+29 lines) | ~437 |
