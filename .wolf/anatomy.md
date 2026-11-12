# anatomy.md

> Auto-maintained by OpenWolf. Last scanned: 2026-11-12T18:33:19.723Z
> Files: 746 tracked | Anatomy hits: 0 | Misses: 0

> Project structure index. Auto-maintained by OpenWolf hooks and daemon.
> Run `openwolf scan` to generate, or wait for the first Claude Code session.
> Status: Pending initial scan

## ./

- `.dockerignore` — Docker ignore rules (~647 tok)
- `.editorconfig` — Editor configuration (~55 tok)
- `.gitignore` — Git ignore rules (~105 tok)
- `.nvmrc` (~2 tok)
- `.pre-commit-config.yaml` (~67 tok)
- `AGENTS.md` — OpenWolf (~75 tok)
- `bench_harvest.py` (~0 tok)
- `CHANGELOG.md` — Changelog (~22316 tok)
- `CLAUDE.md` — OpenWolf (~2750 tok)
- `compose.prod.yaml` — Running SQLDesk from the published image. (~2298 tok)
- `compose.yaml` — This configuration file is for the **development** setup. (~791 tok)
- `cypress.config.js` (~179 tok)
- `Dockerfile` — Docker container definition (~2812 tok)
- `Dockerfile.executor` — The optional interpreter. (~644 tok)
- `Dockerfile.screenshots` — The optional renderer. (~636 tok)
- `GEMINI.md` — OpenWolf (~75 tok)
- `LICENSE` — Project license (~3027 tok)
- `LICENSE.borders` (~59 tok)
- `LICENSE.redash` (~352 tok)
- `Makefile` — Make build targets (~792 tok)
- `manage.py` (~37 tok)
- `NOTICE` (~180 tok)
- `package.json` — Node.js package manifest (~2035 tok)
- `pnpm-workspace.yaml` (~51 tok)
- `pyproject.toml` — Python project configuration (~1853 tok)
- `README.md` — Project documentation (~1499 tok)
- `webpack.config.js` — webpack: optionalRequire, maybeApplyOverrides (~2933 tok)

## .ci/

- `compose.ci.yaml` — Docker Compose: 3 services (~220 tok)
- `compose.cypress.yaml` — Docker Compose: 14 services (~592 tok)
- `Dockerfile.cypress` (~93 tok)

## .github/

- `CONTRIBUTING.md` — Contributing Guide (~1453 tok)
- `PULL_REQUEST_TEMPLATE.md` — What type of PR is this? (~167 tok)
- `SECURITY.md` — Security Policy (~353 tok)

## .github/ISSUE_TEMPLATE/

- `bug_report.md` (~149 tok)
- `config.yml` (~114 tok)
- `feature_request.md` (~74 tok)

## .github/workflows/

- `ci.yml` — CI: Tests (~1773 tok)
- `docker-image.yml` — CI: Docker image (~4165 tok)
- `pages.yml` — CI: Docs site (~509 tok)

## bin/

- `docker-entrypoint` (~1499 tok)
- `run` — Ideally I would use stdin with source, but in older bash versions this (~112 tok)
- `worker.conf` (~286 tok)

## blog/

- `an-agent-that-knows-who-wrote-it.md` — Thirteen tools, in four groups (~3671 tok)
- `README.md` — Project documentation (~611 tok)
- `sqldesk-and-what-it-is-for.md` — What the fork changed (~1951 tok)
- `the-work-a-query-cannot-hold.md` — 1. A churn list that spans two warehouses (~2773 tok)

## charts/sqldesk/

- `Chart.yaml` (~122 tok)
- `README.md` — Project documentation (~1297 tok)
- `values.yaml` — SQLDesk. (~3074 tok)

## charts/sqldesk/templates/

- `_helpers.tpl` (~3631 tok)
- `executor.yaml` — K8s Service (~1598 tok)
- `migrate-job.yaml` — K8s Job (~1027 tok)
- `networkpolicy.yaml` — K8s NetworkPolicy: {{ (~306 tok)
- `NOTES.txt` (~909 tok)
- `postgres.yaml` — K8s PersistentVolumeClaim (~936 tok)
- `redis.yaml` — K8s Service (~1276 tok)
- `screenshots.yaml` — K8s Service: {{ (~945 tok)
- `secret.yaml` — K8s Secret: {{ (~450 tok)
- `server.yaml` — K8s Service: {{ (~1196 tok)
- `uploads.yaml` — K8s PersistentVolumeClaim: {{ (~183 tok)
- `worker.yaml` — K8s Deployment: {{ (~3143 tok)

## client/

- `.babelrc` — Babel configuration (~156 tok)
- `.eslintignore` (~39 tok)
- `.eslintrc.js` — ESLint configuration (~950 tok)
- `.gitignore` — Git ignore rules (~2 tok)
- `bundle-budget.js` — fs: build, tryParse, gzippedSize, main (~1186 tok)
- `bundle-budget.json` (~119 tok)
- `prettier.config.js` — Prettier configuration (~31 tok)
- `tsconfig.json` — TypeScript configuration (~263 tok)

## client/app/

- `.eslintrc.js` — ESLint configuration (~50 tok)
- `index.html` — Declares html (~641 tok)
- `index.js` — Self-hosted via Fontsource rather than loaded from fonts.googleapis.com: (~267 tok)
- `multi_org.html` — Declares html (~579 tok)
- `unsupported.html` — SQLDesk doesn't support your browser (~414 tok)
- `unsupportedRedirect.js` (~45 tok)

## client/app/__tests__/

- `enzyme_setup.js` (~36 tok)
- `fileMock.js` (~136 tok)
- `mocks.js` — Declares date (~438 tok)

## client/app/assets/

- `robots.txt` — robotstxt.org (~8 tok)

## client/app/assets/css/

- `login.css` — Styles: 6 rules, 1 media queries (~294 tok)

## client/app/assets/images/illustrations/

- `readme.md` (~98 tok)

## client/app/assets/less/

- `ant.less` — Styles: 71 rules (~2424 tok)
- `main.less` — LESS Plugins * (~476 tok)
- `server.less` — LESS Plugins * (~313 tok)
- `stylesheet-reach.test.js` — Files declaring a rule for `selector`, ignoring mixin definitions. (~1137 tok)
- `STYLING-README.md` — Styling readme (~77 tok)

## client/app/assets/less/inc/

- `404.less` — Styles: 1 rules, 1 media queries (~276 tok)
- `ace-editor.less` — Styles: 1 rules (~138 tok)
- `alert.less` — Styles: 5 rules (~215 tok)
- `ant-variables.less` — Styles: 93 rules (~1360 tok)
- `base.less` — Styles: 33 rules, 5 media queries (~1655 tok)
- `bootstrap-overrides.less` — Media - Overriding the Media object to 3.2 version in order to prevent issues like text overflow. * (~210 tok)
- `breadcrumb.less` — Styles: 1 rules, 3 media queries (~200 tok)
- `button.less` — ALTERNATIVE BUTTONS * (~692 tok)
- `dropdown.less` — Styles: 3 rules (~464 tok)
- `edit-in-place.less` — Styles: 2 rules (~256 tok)
- `flex.less` — Styles: 32 rules (~518 tok)
- `font.less` — /* -------------------------------------------------------- (~230 tok)
- `form.less` — Styles: 9 rules (~1434 tok)
- `generics.less` — Styles: 33 rules (~1377 tok)
- `header.less` — header { (~2171 tok)
- `ie-warning.less` — Styles: 1 rules (~204 tok)
- `jumbotron.less` — Styles: 1 rules (~18 tok)
- `label.less` — Styles: 9 rules (~158 tok)
- `list-group.less` — Styles: 11 rules (~364 tok)
- `list.less` — Styles: 1 rules (~113 tok)
- `media.less` — Styles: 3 rules, 3 media queries (~596 tok)
- `misc.less` — Styles: 14 rules, 1 media queries (~1340 tok)
- `mixins.less` — Styles: 4 rules (~656 tok)
- `modal.less` — Styles: 5 rules (~256 tok)
- `panel.less` — Styles: 6 rules (~536 tok)
- `popover.less` — Styles: 3 rules (~91 tok)
- `print.less` — Styles: 1 rules, 1 media queries (~270 tok)
- `profile.less` — profile-main { (~1910 tok)
- `progress-bar.less` — Styles: 1 rules (~44 tok)
- `schema-browser.less` — Styles: 1 rules (~524 tok)
- `table.less` — Styles: 12 rules (~1040 tok)
- `tile.less` — Styles: 8 rules, 1 media queries (~503 tok)
- `tokens-root.less` — Styles: 1 rules, 81 vars (~895 tok)
- `tokens-wall.less` — Styles: 22 rules, 33 vars (~1214 tok)
- `tokens-wall.test.js` — WCAG AA for normal text. (~1441 tok)
- `tokens.less` — Styles: 64 rules (~1432 tok)
- `tokens.test.js` — Every swatch in colors.ts, as { name, cssVar, fallback, washVar, wash }. (~921 tok)
- `tooltips.less` — Styles: 1 rules (~24 tok)
- `variables.less` — Form States * (~3042 tok)
- `widgets.less` — Styles: 2 rules (~158 tok)

## client/app/assets/less/inc/less-plugins/

- `for.less` — Styles: 6 rules (~93 tok)

## client/app/assets/less/inc/visualizations/

- `box.less` — Styles: 9 rules (~159 tok)
- `fills-its-box.less` — Styles: 1 rules (~639 tok)
- `map.less` — Styles: 2 rules (~52 tok)
- `misc.less` — Styles: 1 rules (~27 tok)
- `pivot-table.less` — Styles: 2 rules (~34 tok)

## client/app/assets/less/sqldesk/

- `loading-indicator.less` — Styles: 2 rules, 2 animations (~260 tok)
- `query.less` — Styles: 29 rules, 3 media queries (~2536 tok)
- `sqldesk-table.less` — Styles: 16 rules (~492 tok)
- `tags-control.less` — Styles: 1 rules (~80 tok)

## client/app/components/

- `AceEditorInput.jsx` — AceEditorInput (~145 tok)
- `AceEditorInput.less` — Styles: 1 rules (~54 tok)
- `BeaconConsent.jsx` — Text — uses useState (~692 tok)
- `BetaBadge.jsx` — BetaBadge (~382 tok)
- `BetaBadge.less` — Styles: 1 rules (~170 tok)
- `BetaBadge.test.js` — Declares withFeatures (~452 tok)
- `BigMessage.jsx` — BigMessage (~269 tok)
- `CodeBlock.jsx` — success (~516 tok)
- `CodeBlock.less` — Styles: 2 rules (~122 tok)
- `Collapse.jsx` — Collapse (~200 tok)
- `CreateSourceDialog.jsx` — FILE_UPLOAD_TYPES — renders modal (~3409 tok)
- `DateInput.jsx` — DateInput (~312 tok)
- `DateRangeInput.jsx` — DateRangeInput (~361 tok)
- `DateTimeInput.jsx` — DateTimeInput (~354 tok)
- `DateTimeRangeInput.jsx` — DateTimeRangeInput (~414 tok)
- `DialogWrapper.d.ts` — Exports DialogProps, DialogWrapperChildProps, DialogComponentType, wrap (~254 tok)
- `DialogWrapper.jsx` — Wrapper for dialogs based on Ant's <Modal> component. (~1766 tok)
- `DynamicComponent.jsx` — componentsRegistry (~402 tok)
- `EditInPlace.jsx` — newValue (~765 tok)
- `EditParameterSettingsDialog.jsx` — formItemProps — renders form, modal — uses useState, useEffect (~2832 tok)
- `EditParameterSettingsDialog.less` — Styles: 1 rules (~14 tok)
- `EmailSettingsWarning.jsx` — EmailSettingsWarning (~464 tok)
- `FavoritesControl.jsx` — action (~340 tok)
- `Filters.jsx` — ALL_VALUES (~1499 tok)
- `HelpTrigger.jsx` — The documentation, which lives in this repository under `docs/` and is (~1677 tok)
- `HelpTrigger.less` — Styles: 1 rules (~20 tok)
- `HelpTrigger.test.js` — Built the way the application registers it. The drawer version took the (~519 tok)
- `InputWithCopy.jsx` — success (~404 tok)
- `Link.tsx` — DefaultLinkComponent (~473 tok)
- `MarkdownEditor.jsx` — WRITE — uses useState, useMemo (~1213 tok)
- `MarkdownEditor.less` — Styles: 1 rules (~285 tok)
- `MarkdownEditor.test.js` — Declares render (~820 tok)
- `NoTaggedObjectsFound.jsx` — NoTaggedObjectsFound (~180 tok)
- `Paginator.jsx` — MIN_ITEMS_PER_PAGE (~313 tok)
- `ParameterApplyButton.jsx` — ParameterApplyButton (~347 tok)
- `ParameterMappingInput.jsx` — MappingType — renders form (~5450 tok)
- `ParameterMappingInput.less` — Styles: 5 rules (~354 tok)
- `Parameters.jsx` — updateUrl (~1952 tok)
- `Parameters.less` — Styles: 4 rules, 2 media queries (~617 tok)
- `ParameterValueInput.jsx` — multipleValuesProps (~1730 tok)
- `ParameterValueInput.less` — Styles: 3 rules (~135 tok)
- `PlainButton.less` — Styles: 3 rules (~104 tok)
- `PlainButton.tsx` — PlainButton (~236 tok)
- `PreviewCard.jsx` — PreviewCard (~805 tok)
- `proptypes.js` — Exports DataSource, Table, Schema, RefreshScheduleType + 7 more (~890 tok)
- `QueryBasedParameterInput.jsx` — optionValues (~847 tok)
- `QueryLink.jsx` — QueryLink (~593 tok)
- `QueryLink.less` — Styles: 1 rules (~82 tok)
- `QueryLink.test.js` — Declares query (~871 tok)
- `QuerySelector.jsx` — searchFor — uses useState, useEffect (~1774 tok)
- `QuerySelector.jsx.orig` — Exports QuerySelector (~1656 tok)
- `QuerySelector.test.js` — settle: render (~1046 tok)
- `ScheduleControl.jsx` — NEVER — uses useMemo (~1184 tok)
- `ScheduleControl.less` — Qualified with .ant-btn deliberately: antd's own `.ant-btn { display: (~348 tok)
- `ScheduleControl.test.js` — What a stock installation allows: a minute to a month, twenty-one entries. (~1094 tok)
- `SelectItemsDialog.jsx` — ItemsList — renders modal — uses useCallback, useState, useEffect (~1799 tok)
- `SelectItemsDialog.less` — Styles: 1 rules (~42 tok)
- `SelectWithVirtualScroll.tsx` — MIN_LEN_FOR_VIRTUAL_SCROLL (~384 tok)
- `SettingsWrapper.jsx` — wrapSettingsTab (~464 tok)
- `SlackChannelSelect.jsx` — useSlackChannels (~1075 tok)
- `Spinner.jsx` — `inline` follows the surrounding font size; the rest are fixed. (~440 tok)
- `Spinner.less` — Styles: 4 rules, 1 media queries, 1 animations (~357 tok)
- `Spinner.test.js` — Declares that (~696 tok)
- `TagsList.less` — Styles: 2 rules (~274 tok)
- `TagsList.tsx` — TagsList — uses useEffect, useCallback (~841 tok)
- `TimeAgo.jsx` — toMoment — uses useState, useMemo, useEffect (~455 tok)
- `Timer.jsx` — Timer — uses useMemo, useState, useEffect (~432 tok)
- `Timer.test.js` — Declares wrapper (~782 tok)
- `Tooltip.tsx` — Tooltip (~124 tok)
- `TypeLogo.jsx` — A logo is a file named after the type: /static/images/db-logos/<type>.png. Add a (~929 tok)
- `TypeLogo.less` — Styles: 1 rules (~81 tok)
- `TypeLogo.test.js` — Under jest the real one has no folder listing to consult and so says "false" (~1181 tok)
- `TypeLogo.tsx` — A logo is a file named after the type: /static/images/db-logos/<type>.png. Add a (~986 tok)
- `UserAvatar.jsx` — UserAvatar (~724 tok)
- `UserAvatar.less` — Styles: 2 rules (~138 tok)
- `UserAvatar.test.js` — Declares wrapper (~1036 tok)
- `UserGroups.jsx` — UserGroups (~227 tok)
- `UserGroups.less` — Styles: 1 rules (~23 tok)

## client/app/components/ApplicationArea/

- `ErrorMessage.jsx` — getErrorMessageByStatus (~565 tok)
- `ErrorMessage.less` — Styles: 1 rules, 1 media queries (~75 tok)
- `ErrorMessage.test.js` — ErrorMessages: mockAxiosError, expectErrorMessageToBe (~512 tok)
- `ErrorMessageDetails.jsx` — ErrorMessageDetails (~78 tok)
- `handleNavigationIntent.js` — Exports handleNavigationIntent (~205 tok)
- `handleNavigationIntent.test.js` — Declares click (~483 tok)
- `index.jsx` — One report a minute, so a failing timer cannot bury the screen. (~1007 tok)
- `index.test.js` — React: raise, show (~1215 tok)
- `navigateTo.js` — When `replace` is set to `true` - it will just replace current URL (~201 tok)
- `Router.jsx` — generateRouteKey — uses useContext, useState, useRef, useEffect (~1463 tok)
- `routeWithApiKeySession.jsx` — This wrapper modifies `route.render` function and instead of passing `currentRoute` passes an object (~533 tok)
- `routeWithUserSession.tsx` — and — uses useState, useEffect (~984 tok)

## client/app/components/ApplicationArea/ApplicationLayout/

- `DesktopNavbar.jsx` — NavLink — uses useMemo, useState, useEffect (~4194 tok)
- `DesktopNavbar.less` — Styles: 3 rules (~1080 tok)
- `DesktopNavbar.test.js` — mockPermissions: render, places, menu, linksIn (~2971 tok)
- `index.jsx` — ApplicationLayout — uses useRef, useCallback (~380 tok)
- `index.less` — Styles: 2 rules, 4 media queries (~433 tok)
- `MobileNavbar.jsx` — MobileNavbar (~1454 tok)
- `MobileNavbar.less` — Styles: 5 rules (~263 tok)
- `MobileNavbar.test.js` — mockPermissions: links, headings (~1153 tok)
- `VersionInfo.jsx` — VersionInfo (~243 tok)

## client/app/components/EditVisualizationButton/

- `index.jsx` — EditVisualizationButton — renders form (~216 tok)
- `QueryControlDropdown.jsx` — QueryControlDropdown (~1054 tok)
- `QueryResultsLink.jsx` — QueryResultsLink (~370 tok)

## client/app/components/PageHeader/

- `index.jsx` — PageHeader (~131 tok)
- `index.less` — Styles: 1 rules (~88 tok)

## client/app/components/PermissionsEditorDialog/

- `index.jsx` — DEBOUNCE_SEARCH_DURATION — renders modal — uses useCallback, useState, useEffect (~1994 tok)
- `index.less` — Styles: 1 rules (~51 tok)

## client/app/components/Resizable/

- `index.jsx` — Resizable (~1792 tok)
- `index.less` — Styles: 2 rules (~295 tok)

## client/app/components/admin/

- `Layout.jsx` — Layout (~401 tok)
- `layout.less` — Styles: 2 rules (~169 tok)
- `Layout.test.js` — Declares titles (~912 tok)
- `RQStatus.jsx` — CounterCard (~1126 tok)
- `StaleNotice.jsx` — StaleNotice (~333 tok)
- `StatusBlock.jsx` — General (~778 tok)

## client/app/components/cards-list/

- `CardsList.less` — Styles: 7 rules, 4 media queries (~355 tok)
- `CardsList.tsx` — ListItem — uses useState (~789 tok)

## client/app/components/dashboards/

- `AddWidgetDialog.jsx` — VisualizationSelect — renders modal — uses useMemo, useCallback, useState (~1576 tok)
- `AddWidgetDialog.jsx.orig` — VisualizationSelect: AddWidgetDialog (~1471 tok)
- `AddWidgetDialog.test.js` — Declares kindOffered (~591 tok)
- `AutoHeightController.js` — TODO: Revisit this implementation when migrating widget component to React (~807 tok)
- `ChooseWidgetTabsDialog.jsx` — Choose which of a query's visualizations this widget offers as tabs. (~1202 tok)
- `CreateDashboardDialog.jsx` — CreateDashboardDialog — renders modal — uses useState (~1315 tok)
- `CreateDashboardDialog.jsx.orig` — CreateDashboardDialog: handleNameChange, save (~1227 tok)
- `CreateDashboardDialog.less` — The kind choice, under the name field. (~134 tok)
- `CreateDashboardDialog.test.js` — mockFeatures: render, type, save (~1086 tok)
- `dashboard-grid.less` — Styles: 5 rules (~1265 tok)
- `DashboardGrid.jsx` — The dashboard as it is *now*, not as it was when a widget last rendered. (~3574 tok)
- `DashboardGrid.test.js` — The real enum's module pulls in every chart type. (~1080 tok)
- `EditParameterMappingsDialog.jsx` — getParamValuesSnapshot — renders modal (~1016 tok)
- `ExpandedWidgetDialog.jsx` — ExpandedWidgetDialog — renders modal (~379 tok)
- `TextboxDialog.jsx` — ALIGNMENTS — renders modal — uses useState, useEffect, useCallback (~1382 tok)
- `TextboxDialog.less` — Styles: 1 rules (~253 tok)

## client/app/components/dashboards/dashboard-widget/

- `index.js` (~57 tok)
- `LiveCountdown.jsx` — formatRemaining — uses useState, useEffect (~484 tok)
- `LiveCountdown.test.js` — Declares secondsAgo (~571 tok)
- `RestrictedWidget.jsx` — RestrictedWidget (~162 tok)
- `TextboxWidget.jsx` — settingsOf — renders chart — uses useState (~669 tok)
- `TextboxWidget.parity.test.js` — Declares TEXT (~744 tok)
- `TextboxWidget.test.js` — Declares widget (~605 tok)
- `VisualizationWidget.jsx` — visualizationWidgetMenuOptions (~5143 tok)
- `VisualizationWidget.tabs.test.js` — BY_REGION: fakeWidget, mount (~1594 tok)
- `VisualizationWidget.test.js` — Declares fakeWidget (~1160 tok)
- `Widget.jsx` — WidgetDropdownButton (~1156 tok)
- `Widget.less` — Styles: 6 rules (~1991 tok)
- `WidgetFilters.test.js` — Declares widget (~630 tok)

## client/app/components/dynamic-form/

- `DynamicForm.jsx` — ActionType — renders form — uses useReducer, useCallback, useState, useForm (~2073 tok)
- `DynamicForm.less` — Styles: 4 rules (~182 tok)
- `DynamicFormField.jsx` — FieldType (~560 tok)
- `dynamicFormHelper.js` — orderedInputs: normalizeSchema, setDefaultValueToFields, getFields + 3 more (~1363 tok)
- `getFieldLabel.js` — Exports getFieldLabel (~45 tok)

## client/app/components/dynamic-form/fields/

- `AceEditorField.jsx` — AceEditorInput (~225 tok)
- `CheckboxField.jsx` — CheckboxField (~84 tok)
- `ContentField.jsx` — ContentField (~22 tok)
- `FileField.jsx` — FileField (~170 tok)
- `index.js` (~131 tok)
- `InputField.jsx` — InputField (~49 tok)
- `NumberField.jsx` — NumberField (~55 tok)
- `SelectField.jsx` — SelectField (~180 tok)
- `TextAreaField.jsx` — TextAreaField (~53 tok)

## client/app/components/dynamic-parameters/

- `DateParameter.jsx` — DYNAMIC_DATE_OPTIONS (~348 tok)
- `DateRangeParameter.jsx` — DYNAMIC_DATE_OPTIONS (~1178 tok)
- `DynamicButton.jsx` — DynamicButton — uses useRef (~766 tok)
- `DynamicButton.less` — Styles: 3 rules (~163 tok)
- `DynamicDatePicker.jsx` — parameterValue (~966 tok)
- `DynamicDateRangePicker.jsx` — isValidDateRangeValue (~1102 tok)
- `DynamicParameters.less` — Styles: 4 rules (~237 tok)

## client/app/components/empty-state/

- `empty-state.less` — Styles: 3 rules, 1 media queries (~399 tok)
- `EmptyState.d.ts` — Exports StepKey, StepItem, EmptyStateHelpMessageProps, EmptyStateProps, StepProps (~350 tok)
- `EmptyState.jsx` — Step — uses useState, useEffect, useCallback (~1908 tok)
- `EmptyState.test.js` — Declares doneSteps (~432 tok)

## client/app/components/groups/

- `CreateGroupDialog.jsx` — renders modal (~277 tok)
- `DeleteGroupButton.jsx` — deleteGroup (~418 tok)
- `DetailsPageSidebar.jsx` — FeatureToggle — uses useState, useEffect (~1326 tok)
- `GroupName.jsx` — updateGroupName (~267 tok)
- `ListItemAddon.jsx` — ListItemAddon (~374 tok)

## client/app/components/items-list/

- `ItemsList.tsx` — ControllerType (~2204 tok)

## client/app/components/items-list/classes/

- `ItemsFetcher.js` — Exports PlainListFetcher, PaginatedListFetcher (~1164 tok)
- `ItemsFetcher.test.js` — ALERTS: matches, build (~1552 tok)
- `ItemsSource.d.ts` — Exports ItemsSourceOptions, GetResourceContext, GetResourceRequest, ItemsPage + 2 more (~417 tok)
- `ItemsSource.js` — Exports ItemsSource, ResourceItemsSource (~1692 tok)
- `Paginator.js` — Exports Paginator (~387 tok)
- `Sorter.js` — Exports compile, parse (~479 tok)
- `StateStorage.js` — Exports StateStorage, UrlStateStorage (~484 tok)

## client/app/components/items-list/components/

- `EmptyState.jsx` — Default "list empty" message for list pages (~93 tok)
- `ItemsTable.jsx` — `this` refers to previous function in the chain (`Columns.***`). (~1945 tok)
- `ListItemActions.jsx` — canManagePermissions — uses useCallback (~1202 tok)
- `ListItemActions.less` — Styles: 2 rules (~153 tok)
- `ListItemActions.test.js` — notification: menu (~1219 tok)
- `ListPage.jsx` — Shell — uses useState, useEffect, useCallback (~1395 tok)
- `ListPage.less` — Styles: 33 rules (~1498 tok)
- `ListPageControls.jsx` — SearchControl — renders table (~1732 tok)
- `ListPageControls.less` — Styles: 3 rules (~456 tok)
- `ListPageControls.test.js` — ColumnsControl hangs its contents off a Dropdown overlay, which antd only (~1778 tok)
- `LoadingState.jsx` — Default "loading" message for list pages. (~235 tok)
- `Sidebar.jsx` — SearchInput — uses useState, useEffect, useCallback (~1086 tok)

## client/app/components/items-list/hooks/

- `useItemsListExtraActions.js` — Exports useItemsListExtraActions (~716 tok)

## client/app/components/layouts/

- `content-with-sidebar.less` — Styles: 1 rules, 1 media queries (~184 tok)
- `ContentWithSidebar.jsx` — propTypes (~330 tok)

## client/app/components/queries/

- `add-to-dashboard-dialog.less` — Styles: 2 rules (~183 tok)
- `AddToDashboardDialog.jsx` — AddToDashboardDialog — renders modal — uses useState, useEffect (~1296 tok)
- `ConfirmQueryDialog.jsx` — ConfirmQueryDialog — renders modal — uses useState (~720 tok)
- `CronScheduleDialog.jsx` — Why this exists rather than a cron library: the server validates with (~1447 tok)
- `CronScheduleDialog.less` — Styles: 1 rules (~290 tok)
- `CronScheduleDialog.test.js` — This mirrors croniter, which is the authority -- the server rejects anything (~552 tok)
- `EmbedQueryDialog.jsx` — renders form, modal (~1176 tok)
- `EmbedQueryDialog.less` — Styles: 2 rules (~40 tok)
- `QueryHealth.jsx` — A scheduled query is called stale once it has missed its window by a clear (~680 tok)
- `QueryHealth.less` — Styles: 1 rules (~168 tok)
- `QueryHealth.test.js` — Declares NOW (~676 tok)
- `SchedulePhrase.jsx` — schedule (~580 tok)
- `SchedulePhrase.less` — Carried over from ScheduleDialog.css, which went with the dialog. These were (~59 tok)
- `SchemaBrowser.jsx` — SchemaItemColumnType — renders modal (~3445 tok)
- `useDataSourceNames.js` — Exports useDataSourceNames (~330 tok)

## client/app/components/queries/ApiKeyDialog/

- `index.jsx` — ApiKeyDialog — renders modal — uses useState, useCallback, useMemo (~860 tok)
- `index.less` — Styles: 1 rules (~74 tok)

## client/app/components/queries/QueryEditor/

- `ace.js` — Exports updateSchemaCompleter (~949 tok)
- `AutocompleteToggle.jsx` — AutocompleteToggle — uses useCallback (~392 tok)
- `AutoLimitCheckbox.jsx` — AutoLimitCheckbox — uses useCallback (~322 tok)
- `index.jsx` — Mirrors @font-mono in assets/less/inc/tokens.less. Ace cannot take a CSS (~1792 tok)
- `index.less` — Styles: 1 rules (~137 tok)
- `QueryEditorControls.jsx` — ButtonTooltip — uses useEffect (~1834 tok)
- `QueryEditorControls.less` — Styles: 1 rules (~346 tok)

## client/app/components/queries/QueryHistoryDialog/

- `diffLines.js` — The lines of `after`, each marked against `before`. (~743 tok)
- `diffLines.test.js` — Declares marked (~584 tok)
- `index.jsx` — The current query, in the shape a recorded version has. (~2238 tok)
- `index.less` — Styles: 2 rules (~528 tok)
- `index.test.js` — version: query, render (~1616 tok)

## client/app/components/queries/editor-components/

- `editorComponents.js` — Exports QueryEditorComponents, registerEditorComponent, getEditorComponents (~230 tok)
- `index.js` — default (~187 tok)

## client/app/components/queries/editor-components/databricks/

- `DatabricksSchemaBrowser.jsx` — DatabricksSchemaBrowser — uses useState, useMemo, useCallback, useEffect (~1478 tok)
- `DatabricksSchemaBrowser.less` — Styles: 3 rules (~345 tok)
- `useDatabricksSchema.js` — Exports useDatabricksSchema (~1983 tok)

## client/app/components/query-snippets/

- `QuerySnippetDialog.jsx` — QuerySnippetDialog — renders modal — uses useCallback (~749 tok)

## client/app/components/tags-control/

- `EditTagsDialog.jsx` — EditTagsDialog — renders modal — uses useState, useEffect (~601 tok)
- `TagsControl.jsx` — tags (~962 tok)

## client/app/components/visualizations/

- `EditVisualizationDialog.jsx` — updateQueryVisualizations — renders chart, modal — uses useRef, useState, useMemo, useEffect (~2557 tok)
- `EditVisualizationDialog.less` — Styles: 1 rules, 1 media queries (~83 tok)
- `visualizationComponents.jsx` — Charts are normally built only once they come near the viewport. A page (~884 tok)
- `VisualizationDescription.jsx` — VisualizationDescription — renders chart — uses useRef, useState, useEffect (~596 tok)
- `VisualizationDescription.less` — Under the panel's title, quieter than it. `white-space` is set because a (~159 tok)
- `VisualizationDescription.test.js` — Declares wrapper (~575 tok)
- `VisualizationName.jsx` — A visualization's own name, or null when it does not have one worth saying: (~429 tok)
- `VisualizationName.less` — Styles: 2 rules (~138 tok)
- `VisualizationName.test.js` — Declares named (~300 tok)
- `VisualizationRenderer.jsx` — combineFilters — uses useState, useRef, useEffect, useMemo (~972 tok)

## client/app/config/

- `antd-spinner.jsx` — Every antd <Spin> in the app, in one place. The indicator itself says (~121 tok)
- `dashboard-grid-options.js` — Twenty-four columns rather than twelve, and rows half as tall, so a widget (~207 tok)
- `dashboard-grid-options.test.js` — Declares pixelHeight (~1790 tok)
- `index.js` — Ensure that this image will be available in assets folder (~353 tok)

## client/app/extensions/

- `.gitkeep` (~0 tok)

## client/app/lib/

- `accessibility.ts` — Exports srNotify (~279 tok)
- `browserNoise.js` — Noise the browser reports that the person reading the page cannot act on. (~494 tok)
- `browserNoise.test.js` (~406 tok)
- `calculateTextWidth.ts` — Exports calculateTextWidth (~209 tok)
- `initialsTile.js` — The same label always gets the same colour, between renders and reloads. (~494 tok)
- `lazyPage.js` — How long a reload counts for, so a still-broken build does not loop. (~922 tok)
- `lazyPage.test.js` — fakeStorage: chunkError (~1248 tok)
- `localOptions.js` — PREFIX: get, set (~115 tok)
- `logoAssets.js` — `/static/images/db-logos/pg.png` and `static/images/destinations/slack.png` both. (~630 tok)
- `logoAssets.test.js` — Declares known (~390 tok)
- `markdown.js` — Exports toHtml (~558 tok)
- `markdown.test.js` — Declares html (~1097 tok)
- `queryFormat.test.js` — Declares unsupportedSyntax (~671 tok)
- `queryFormat.ts` — Exports isFormatQueryAvailable, formatQuery (~189 tok)
- `serverClock.js` — Exports syncServerClock, serverNow, resetServerClock (~182 tok)
- `useQueryResultData.js` — Exports useQueryResultData (~313 tok)
- `utils.js` — Formats number to string (~1648 tok)

## client/app/lib/hooks/

- `useFullscreenHandler.js` — Exports useFullscreenHandler (~152 tok)
- `useImmutableCallback.js` — This hook wraps a potentially changeable function object and always returns the same (~203 tok)
- `useLazyRef.ts` — Exports useLazyRef (~74 tok)
- `usePolledData.js` — 401/403 mean something a refresh cannot fix. (~1043 tok)
- `usePolledData.test.js` — Lets the promises in flight settle. (~1526 tok)
- `useScreenshotMode.js` — Has every widget on this dashboard finished, so the page is worth capturing? (~2486 tok)
- `useScreenshotMode.test.js` — Declares loaded (~609 tok)
- `useSearchResults.js` — Exports useSearchResults (~282 tok)
- `useUniqueId.ts` — Exports useUniqueId (~58 tok)
- `useUnsavedChangesAlert.js` — Exports useUnsavedChangesAlert (~282 tok)

## client/app/lib/sql-formatter/

- `LICENSE` — Project license (~292 tok)
- `README.md` — Project documentation (~287 tok)
- `sqlFormatter.d.ts` — Standard SQL unless one of the dialects below is named. (~198 tok)
- `sqlFormatter.js` — Format whitespaces in a query to make it easier to read. (~359 tok)

## client/app/lib/sql-formatter/core/

- `Formatter.js` — Exports Formatter (~2102 tok)
- `Indentation.js` — Manages indentation levels. (~498 tok)
- `InlineBlock.js` — Bookkeeper for inline blocks. (~728 tok)
- `Params.js` — Handles placeholder replacement with given params. (~207 tok)
- `Tokenizer.js` — Exports Tokenizer (~2992 tok)
- `tokenTypes.js` — Constants for token types (~129 tok)

## client/app/lib/sql-formatter/languages/

- `Db2Formatter.js` — Exports Db2Formatter (~2117 tok)
- `N1qlFormatter.js` — Exports N1qlFormatter (~964 tok)
- `PlSqlFormatter.js` — Exports PlSqlFormatter (~1611 tok)
- `StandardSqlFormatter.js` — Exports StandardSqlFormatter (~1525 tok)

## client/app/pages/

- `index.js` (~215 tok)
- `settings.menu.js` (~898 tok)
- `settings.routes.jsx` — The tabs and the navbar link, which have to exist before any of these (~1718 tok)

## client/app/pages/admin/

- `admin.routes.jsx` — Overview (~879 tok)
- `adminTabs.js` — The tabs this install shows, in order. (~1196 tok)
- `Audit.jsx` — A count, grouped so four figures do not read as one long number. (~1677 tok)
- `Audit.test.js` — Declares strip (~670 tok)
- `Catalog.jsx` — DescriptionCell — renders table — uses useState, useCallback, useEffect, useMemo (~7821 tok)
- `catalog.less` — Styles: 3 rules (~429 tok)
- `Jobs.jsx` — queueCounters (~1151 tok)
- `OutdatedQueries.jsx` — OutdatedQueriesPage (~1498 tok)
- `RunningQueries.jsx` — REFRESH_MS — renders table — uses useState, useRef, useCallback, useEffect (~1258 tok)
- `Storage.jsx` — readable — renders table — uses useCallback, useState, useEffect (~2656 tok)
- `storage.less` — Admin -> Storage. The numbers that were only visible on the filesystem. (~197 tok)
- `Streams.jsx` — Numbers — renders table, chart — uses useState, useCallback, useEffect (~3039 tok)
- `streams.less` — Admin -> Streams. Numbers that move on their own, so the page polls. (~152 tok)
- `Streams.test.js` — stream: render (~1106 tok)
- `system-status.less` — Styles: 1 rules, 2 media queries (~206 tok)
- `SystemStatus.jsx` — API routes: GET (1 endpoints) (~642 tok)

## client/app/pages/admin/overview/

- `Overview.jsx` — REFRESH_MS — uses useState, useRef, useCallback, useEffect (~2257 tok)
- `overview.less` — Styles: 26 rules, 2 media queries (~1346 tok)
- `Overview.test.js` — mockGet: render, panels (~604 tok)
- `pressure.js` — Nothing to measure against -- Redis with no maxmemory, say. (~776 tok)
- `pressure.test.js` (~901 tok)

## client/app/pages/alert/

- `Alert.jsx` — defaultNameBuilder (~2051 tok)
- `AlertEdit.jsx` — renders form (~1568 tok)
- `AlertNew.jsx` — renders form (~1452 tok)
- `alerts.routes.jsx` — AlertsList (~410 tok)
- `AlertView.jsx` — AlertState — renders form (~1920 tok)
- `modes.js` — Declares MODES (~84 tok)

## client/app/pages/alert/components/

- `AlertAttachments.jsx` — MAX_ATTACHMENTS (~1520 tok)
- `AlertAttachments.less` — Styles: 5 rules (~294 tok)
- `AlertDestinations.jsx` — USER_EMAIL_DEST_ID (~2080 tok)
- `AlertDestinations.less` — Styles: 2 rules (~352 tok)
- `AlertHistory.jsx` — Fire (~856 tok)
- `AlertHistory.test.js` — Declares fire (~937 tok)
- `Criteria.jsx` — CONDITIONS (~1880 tok)
- `Criteria.less` — Styles: 2 rules (~282 tok)
- `HorizontalFormItem.jsx` — HorizontalFormItem — renders form (~215 tok)
- `MenuButton.jsx` — MenuButton — uses useState, useCallback (~679 tok)
- `NotificationTemplate.jsx` — normalizeCustomTemplateData (~1349 tok)
- `NotificationTemplate.less` — Styles: 1 rules (~167 tok)
- `Query.jsx` — QueryFormItem (~711 tok)
- `Query.less` — Styles: 3 rules, 1 media queries (~98 tok)
- `Rearm.jsx` — DURATIONS — uses useState, useEffect (~1084 tok)
- `Rearm.less` — Styles: 1 rules (~34 tok)
- `Title.jsx` — Title (~367 tok)
- `Title.less` — Styles: 1 rules, 2 media queries (~116 tok)

## client/app/pages/alerts/

- `AlertsList.jsx` — STATE_CLASS (~2133 tok)

## client/app/pages/dashboards/

- `dashboard-folders.less` — Styles: 2 rules (~278 tok)
- `dashboard-list.css` — Styles: 1 rules, 1 media queries (~117 tok)
- `dashboard-print.less` — Styles: 1 rules, 1 media queries (~467 tok)
- `DashboardFolders.jsx` — FolderDialog — renders modal — uses useState, useEffect, useCallback (~2183 tok)
- `DashboardFolders.test.js` — settle: render (~1289 tok)
- `DashboardList.jsx` — VIEWS — renders chart — uses useRef, useMemo (~3761 tok)
- `DashboardList.test.js` — mockPermissions: settle, routeFor, render (~1277 tok)
- `DashboardPage.jsx` — AddWidgetContainer — renders chart — uses useState, useEffect (~2566 tok)
- `DashboardPage.less` — Styles: 9 rules (~543 tok)
- `dashboards.routes.jsx` — DashboardFolders (~719 tok)
- `PublicDashboardPage.branding.test.js` — Declares PAGES (~383 tok)
- `PublicDashboardPage.jsx` — PublicDashboard (~1057 tok)
- `PublicDashboardPage.less` — Styles: 1 rules (~148 tok)
- `WallDashboardPage.jsx` — A dashboard for a screen on the wall: dark, no chrome, big type, and able to (~1651 tok)
- `WallDashboardPage.less` — Styles: 2 rules (~1967 tok)

## client/app/pages/dashboards/components/

- `DashboardEditControl.test.js` — config: render, click (~1601 tok)
- `DashboardFilters.jsx` — DashboardFilters (~794 tok)
- `DashboardFilters.less` — Styles: 2 rules (~602 tok)
- `DashboardFilters.test.js` — param: config (~667 tok)
- `DashboardFolderMenu.test.js` — Declares folderItems (~721 tok)
- `DashboardHeader.jsx` — Whether this person may move this dashboard between folders. (~5499 tok)
- `DashboardHeader.jsx.orig` — Whether this person may move this dashboard between folders. (~5132 tok)
- `DashboardHeader.less` — Styles: 2 rules, 3 media queries, 1 animations (~581 tok)
- `DashboardListEmptyState.tsx` — DashboardListEmptyState (~654 tok)
- `DashboardPageTitle.test.js` — Declares render (~634 tok)
- `LiveBadge.intervals.test.js` (~462 tok)
- `LiveBadge.jsx` — "● Live · every 30 seconds", or "Paused by Iqbal". The dot pulses while (~661 tok)
- `LiveBadge.less` — Styles: 3 rules, 1 media queries, 1 animations (~274 tok)
- `LiveBadge.test.js` — Declares text (~530 tok)
- `SendableNotice.jsx` — useSendable (~724 tok)
- `SendToSlackDialog.jsx` — SendToSlackDialog — renders modal (~993 tok)
- `ShareDashboardButton.jsx` — ShareDashboardButton — uses useState, useCallback (~2415 tok)
- `ShareDashboardButton.test.js` — Declares menuText (~698 tok)
- `ShareDashboardDialog.jsx` — API_SHARE_URL — renders form, modal (~1102 tok)
- `StreamMarker.jsx` — A rate a person can read, rather than seventeen digits of false precision. (~1214 tok)
- `StreamMarker.less` — Styles: 5 rules (~661 tok)
- `StreamMarker.test.js` — Declares aStream (~1741 tok)
- `SubscribeDashboardDialog.jsx` — INTERVALS — renders table, modal (~2585 tok)

## client/app/pages/dashboards/export/

- `capture.test.js` — SAFARI_LIMIT: grid (~1339 tok)
- `compose.js` — Exports PAGE_FURNITURE (~1480 tok)
- `index.js` — Exports MAX_WIDGETS, TooBigToExport, tooBigToExport, exportSizeProblem + 4 more (~5937 tok)
- `singleImagePdf.js` — Exports fitToPage (~1073 tok)
- `singleImagePdf.test.js` — A byte sequence standing in for JPEG data, including bytes that would break (~886 tok)
- `tiles.test.js` — Declares pageOf (~899 tok)

## client/app/pages/dashboards/hooks/

- `useDashboard.js` — A live dashboard shows the result the server makes, which uses the saved (~3844 tok)
- `useDashboard.test.js` — Every freshness a widget was asked for, in order. (~2099 tok)
- `useDashboardCycle.js` — How often the progress bar moves. Not how often the dashboard changes. (~426 tok)
- `useDashboardCycle.test.js` — Move both the fake clock and Date.now, which the hook reads. (~1200 tok)
- `useDuplicateDashboard.js` — Exports useDuplicateDashboard (~401 tok)
- `useEditModeHandler.js` — Editing a dashboard's layout, and saving it when asked to. (~1386 tok)
- `useEditModeHandler.test.js` — Report a layout the way the grid does, keyed by widget id. (~2538 tok)
- `useLiveDashboard.js` — When to check in next: the usual interval, sooner if a widget falls due (~2077 tok)
- `useLiveDashboard.test.js` — widget: secondsAgo, Harness, setVisibility, flush, mountHarness (~2818 tok)
- `useRefreshRateHandler.js` — An ordinary dashboard's auto-refresh is a timer in every open tab, so it (~601 tok)
- `useRefreshRateHandler.test.js` (~178 tok)
- `useRunningStreams.js` — Which running stream a widget is drawn from, or null. (~1372 tok)
- `useWallScroll.js` — How often the scroll position is recomputed. (~671 tok)
- `useWallScroll.test.js` — at: render, Probe, tick (~1165 tok)
- `useWallTheme.js` — Put the page into the dark wall theme, and take it out again on the way. (~404 tok)

## client/app/pages/data-sources/

- `DataSourcesList.jsx` — DataSourcesListComponent (~1380 tok)
- `DataSourcesList.test.js` — Declares sources (~398 tok)
- `EditDataSource.jsx` — DESCRIPTION_FIELD (~2133 tok)
- `UploadedFilesPanel.jsx` — formatSize — renders modal (~1625 tok)

## client/app/pages/destinations/

- `DestinationsList.jsx` — target (~1141 tok)
- `EditDestination.jsx` — message (~964 tok)

## client/app/pages/groups/

- `GroupDataSources.jsx` — menu (~2389 tok)
- `GroupMembers.jsx` — alreadyAddedUsers (~1955 tok)
- `GroupsList.jsx` — canRemove (~1282 tok)

## client/app/pages/home/

- `Home.jsx` — DeprecatedEmbedFeatureAlert — uses useState, useEffect (~1295 tok)
- `Home.less` — Styles: 15 rules, 1 media queries (~943 tok)
- `Home.title.test.js` — read: declarations (~472 tok)

## client/app/pages/home/components/

- `FavoritesList.jsx` — FavoriteList — uses useState, useEffect (~881 tok)
- `HomeCounters.jsx` — Each tile is a link, because a count is nearly always the start of a (~818 tok)
- `ScheduledQueriesList.jsx` — Slowest first, which is what the endpoint returns. A scheduled query is one (~763 tok)
- `ScheduledQueriesList.test.js` — Declares QUERY (~795 tok)

## client/app/pages/mcp/

- `mcp.less` — Styles: 2 rules (~503 tok)
- `mcp.routes.jsx` — MyMcp (~191 tok)
- `McpHome.jsx` — OUTCOME — renders table — uses useState, useCallback, useEffect (~2611 tok)
- `MyMcp.jsx` — OUTCOME — renders table — uses useState, useCallback, useEffect (~1733 tok)
- `MyMcp.test.js` — CALL: mine, render (~1197 tok)

## client/app/pages/notebooks/

- `CellFigure.jsx` — CellFigure (~974 tok)
- `CellVisualizationDialog.jsx` — CellVisualizationDialog — renders modal (~1459 tok)
- `EditableTitle.jsx` — EditableTitle (~730 tok)
- `Notebook.jsx` — NotebookPage (~3690 tok)
- `notebook.less` — Styles: 48 rules (~6054 tok)
- `Notebook.test.js` — Notebook: fixture, open (~1074 tok)
- `NotebookCell.jsx` — EARLIER_CELLS (~12595 tok)
- `NotebookCell.test.js` — Notebook: aCell, mount (~1778 tok)
- `NotebookHelpDialog.jsx` — Rule — renders modal (~1235 tok)
- `NotebookList.jsx` — subtitle (~1706 tok)
- `NotebookScheduleDialog.jsx` — PRESETS — renders modal (~1039 tok)
- `popup.js` — Declares popupInPage (~297 tok)
- `ShareNotebookButton.jsx` — ShareNotebookButton (~1541 tok)
- `ShareNotebookButton.test.js` — exportModule: aNotebook, mountButton, choose (~1065 tok)

## client/app/pages/queries-list/

- `QueriesList.jsx` — VIEWS (~4032 tok)
- `QueriesList.test.js` — mockPermissions: settle, render, viewHrefs (~1226 tok)

## client/app/pages/queries/

- `queries.less` — Styles: 2 rules (~361 tok)
- `queries.routes.jsx` — QuerySourcePage — renders chart (~605 tok)
- `QuerySource.jsx` — chooseDataSourceId (~8147 tok)
- `QuerySource.less` — Styles: 2 rules, 1 media queries (~536 tok)
- `QueryView.jsx` — QueryView — uses useState, useCallback, useEffect (~3068 tok)
- `QueryView.less` — Styles: 1 rules, 1 media queries (~502 tok)
- `VisualizationEmbed.jsx` — VisualizationEmbedHeader — renders chart — uses useState, useEffect, useCallback (~2820 tok)

## client/app/pages/queries/components/

- `QueryExecutionMetadata.jsx` — isCancelButtonAvailable (~1592 tok)
- `QueryExecutionMetadata.less` — Styles: 1 rules (~101 tok)
- `QueryExecutionStatus.jsx` — Shared with QueryExecutionMetadata, which shows the same words in the footer (~625 tok)
- `QueryMetadata.jsx` — QueryMetadata (~1117 tok)
- `QueryMetadata.less` — Styles: 1 rules, 2 media queries (~490 tok)
- `QueryPageHeader.jsx` — getQueryTags — uses useMemo (~3180 tok)
- `QueryPageHeader.less` — Styles: 1 rules, 2 media queries (~295 tok)
- `QuerySourceAlerts.jsx` — QuerySourceAlerts (~854 tok)
- `QuerySourceAlerts.less` — Styles: 2 rules (~316 tok)
- `QuerySourceDropdown.jsx` — QuerySourceDropdown (~408 tok)
- `QuerySourceDropdownItem.jsx` — QuerySourceDropdownItem (~238 tok)
- `QuerySourceTypeIcon.jsx` — QuerySourceTypeIcon (~116 tok)
- `QueryViewButton.jsx` — QueryViewButton — uses useState, useMemo, useEffect (~482 tok)
- `QueryVisualizationTabs.jsx` — EmptyState — renders chart — uses useCallback, useMemo, useEffect, useState (~1830 tok)
- `QueryVisualizationTabs.less` — Styles: 3 rules (~1046 tok)
- `StreamStatus.jsx` — How long it has been running, in the largest unit that still reads. (~2184 tok)
- `StreamStatus.less` — Styles: 5 rules (~505 tok)
- `StreamStatus.test.js` — STREAM: render (~1787 tok)
- `wrapQueryPage.jsx` — wrapQueryPage — uses useState, useEffect (~359 tok)

## client/app/pages/queries/hooks/

- `useAddNewParameterDialog.js` — Exports useAddNewParameterDialog (~238 tok)
- `useAddToDashboardDialog.js` — Exports useAddToDashboardDialog (~124 tok)
- `useAddVisualizationDialog.js` — Exports useAddVisualizationDialog (~251 tok)

## client/app/pages/streams/

- `streams.routes.jsx` — QuerySourcePage (~1109 tok)

## client/app/services/

- `notebook.js` — API routes: GET, POST, DELETE (11 endpoints) (~462 tok)
- `query.js` — API routes: GET, DELETE, POST (14 endpoints) (~3463 tok)
- `widget.js` — The visualizations this widget can show, its own first. (~3302 tok)

## client/cypress/integration/settings/

- `settings_tabs_spec.js` — API routes: GET (1 endpoints) (~692 tok)

## docs/

- `_card.html` — card (~748 tok)
- `_mark-options.html` — Mark options — SQLDesk (~2902 tok)
- `index.html` — SQLDesk (~12911 tok)
- `releases.html` — Releases — SQLDesk (~7526 tok)

## docs/assets/

- `search.css` — Styles: 26 rules (~1054 tok)
- `search.js` — load: escape, mark, snippet + 5 more (~2728 tok)

## docs/guide/

- `alerts.html` — Alerts — SQLDesk docs (~3635 tok)
- `deploying.html` — Deploying — SQLDesk docs (~13887 tok)
- `mcp.html` — MCP — SQLDesk docs (~8547 tok)
- `notebooks.html` — Notebooks — SQLDesk docs (~2382 tok)
- `queries.html` — Queries and parameters — SQLDesk docs (~2202 tok)
- `streams.html` — Streams — SQLDesk docs (~4736 tok)
- `visualizations.html` — Visualizations — SQLDesk docs (~3720 tok)

## docs/tools/

- `chrome.py` — site_nav, rewrite_topbar_nav, nav, neighbours (~2628 tok)
- `search.py` — text, sections, build, main (~1147 tok)

## examples/

- `kafka-demo.yaml` — A Kafka broker and two producers, for trying streams out. (~1112 tok)
- `mailpit.yaml` — A mail server that catches everything and delivers nothing. (~452 tok)
- `values-production.yaml` — SQLDesk on a real Kubernetes cluster. (~1505 tok)

## executor/

- `runner.py` — limits, scrubbed, run_cell, load_input (~2960 tok)
- `service.py` — API router (~4058 tok)
- `spark.py` — TooMuchToCollect: configured, session, attached, stop + 2 more (~1307 tok)

## migrations/

- `env.py` — this is the Alembic Config object, which provides (~921 tok)

## migrations/versions/

- `4b9e2d81c705_notebook_run_printed.py` — What a notebook cell printed, kept alongside its table. (~198 tok)
- `5c1f7a92b4d8_notebook_cell_title.py` — A title for a notebook cell, separate from the name other cells use. (~204 tok)
- `6d2a8e34f71b_notebook_schedule.py` — A notebook can run itself on a cron. (~339 tok)
- `a1c7f30e95bd_dashboard_kind.py` — A dashboard declares whether it is streaming (~738 tok)
- `a8d3f6c1e924_subscription_slack_channel.py` — A dashboard subscription can post to a Slack channel (~257 tok)
- `d4b2a8e61f37_stream_value_formats.py` — A stream can read Avro and Protobuf, not only JSON (~318 tok)
- `d7e3ae10b9a9_slack_token_bytea.py` — The Slack bot token is stored as bytes, where an install has it as text (~741 tok)
- `f3a71c20e9d5_alert_fires.py` — An alert keeps a history of when it fired (~498 tok)
- `f9b3d61c48a7_slack_workspace.py` — The Slack app's bot token. (~577 tok)

## plan/

- `0.7-nav.md` — The navigation restructure (~2242 tok)
- `0.7.10-plan.md` — 0.7.10 (~919 tok)
- `0.7.7-plan.md` — SQLDesk 0.7.7 — scope agreed with Iqbal, 2026-10-23 (~5858 tok)
- `0.7.7-verification.md` — 0.7.7 — what was exercised, and what it answered (~2010 tok)
- `0.7.8-plan.md` — 0.7.8 (~1622 tok)
- `0.8-plan.md` — SQLDesk 0.8.0 — Notebooks (~1133 tok)
- `0.8.1-plan.md` — SQLDesk 0.8.1 — Notebooks people can live in (~1296 tok)
- `agent-context.md` — What an agent is given, and what it costs (~1666 tok)
- `local-dev.md` — The local cluster, and what keeps breaking (~2713 tok)
- `open-questions.md` — Waiting on Iqbal (~614 tok)
- `README.md` — Project documentation (~508 tok)

## sqldesk/

- `alerting.py` — condition, latest_value, headline, how_often (~1401 tok)
- `notebooks.py` — name_problem, staleness, walk, missing_inputs (~1490 tok)
- `one_page.py` — grid_height, size_check, too_big_to_send (~1700 tok)
- `pools.py` — _Lock: pool_for, budget, held, in_use + 3 more (~2550 tok)
- `slack.py` — check, channels, find_channel, upload (~3428 tok)

## sqldesk/cli/

- `demo.py` — seed, remove, run (~1280 tok)
- `users.py` — build_groups, grant_admin, create, create_root (~3433 tok)

## sqldesk/demo/

- `__init__.py` — store_path, build_the_data, seed, remove (~2327 tok)
- `content.py` — Declares appears (~3409 tok)
- `data.py` — statements (~1677 tok)

## sqldesk/destinations/

- `slack.py` — Slack: configuration_schema, icon, notify (~1580 tok)

## sqldesk/handlers/

- `alerts.py` — AlertResource: require_access_to_attachments, can_see_dashboard, get, post + 10 more (~2597 tok)
- `api.py` — ApiExt: add_org_resource, handle_error, json_representation (~5372 tok)
- `authentication.py` — get_google_auth_url, render_token_login_page, invite, reset (~5769 tok)
- `dashboards.py` — DashboardListResource: filter_by_kind, get, post, get + 2 more (~8039 tok)
- `destinations.py` — DestinationTypeListResource: get, get, post, delete + 2 more (~1539 tok)
- `notebooks.py` — NotebookListResource: serialize_notebook, serialize_cell, get, post + 5 more (~4498 tok)
- `queries.py` — QuerySearchResource: filter_by_kind, format_sql_query, require_valid_schedule, get + 7 more (~8402 tok)
- `slack.py` — SlackSettingsResource: get, post, delete, get + 2 more (~3362 tok)
- `widgets.py` — WidgetListResource: clean_tabs, apply_tabs, post, post + 1 more (~2185 tok)

## sqldesk/mcp/

- `__init__.py` — McpError: note_write, take_write_note (~36293 tok)
- `layout.py` — size_of, positions (~926 tok)

## sqldesk/metrics/

- `prometheus.py` — Metrics: enabled, authorised, add, render + 1 more (~2448 tok)

## sqldesk/models/

- `__init__.py` — ScheduledQueriesExecutions: refresh, update, get, to_dict + 16 more (~41472 tok)
- `users.py` — PermissionsCheckMixin: sync_last_active_at, update_user_active_at, init_app, has_permission + 28 mor (~4407 tok)

## sqldesk/notebooks/

- `interpreter.py` — NoInterpreter: configured, references, headers, session_for + 6 more (~2794 tok)
- `run.py` — CannotRun: references, earlier, why_it_cannot_run, run_sql_cell (~2509 tok)
- `store.py` — TooMuch: connection, directory, seal, close + 11 more (~3736 tok)

## sqldesk/query_runner/

- `__init__.py` — deferred: installed, split_sql_statements, strip_trailing_comments, strip_trailing_semicolon + 14 mo (~6766 tok)
- `prometheus.py` — Prometheus: split_query_body, sample_time, api_error, sample_value + 9 more (~7500 tok)

## sqldesk/serializers/

- `__init__.py` — Serializer: streaming_data_source_ids, public_widget, public_dashboard, serialize_dashboard_subscrip (~5539 tok)

## sqldesk/settings/

- `__init__.py` (~12212 tok)

## sqldesk/streams/

- `decode.py` — SchemaError: is_problem, stored, load, decode + 1 more (~8674 tok)

## sqldesk/tasks/

- `alerts.py` — notify_subscriptions, should_notify, check_alerts_for_query (~1051 tok)
- `notebooks.py` — run_cell (~901 tok)

## tests/

- `factories.py` — ModelFactory: create, user, data_source, create_org + 17 more (~2803 tok)
- `test_audit.py` — AuditTestCase: ran, setUp, test_an_empty_month_is_zero_rather_than_an_error, test_it_counts_the_exec (~2305 tok)
- `test_build_hygiene.py` — /__pycache__` was shipping. (~824 tok)
- `test_chart.py` — TestTheMigrationJob: template, metadata_name, test_its_name_is_the_same_on_every_upgrade, test_the_p (~975 tok)
- `test_cli.py` — DataSourceCommandTests: test_interactive_new, test_options_new, test_bad_type_new, test_bad_options_ (~7326 tok)
- `test_demo.py` — TestTheDemoCoversEveryVisualization: registered_types, test_every_registered_type_is_demonstrated, t (~2551 tok)
- `test_discovery_documents.py` — TestTheKeepListMatchesTheCode: documents_the_dockerfile_keeps, documents_the_code_asks_for, test_eve (~1084 tok)
- `test_executor_spark.py` — FakeFrame: limit, toPandas, test_nothing_is_opened_until_something_is_asked_of_it, test_the_first_re (~1845 tok)
- `test_executor.py` — ExecutorTestCase: parquet_of, setUpClass, setUp, tearDown + 27 more (~3898 tok)
- `test_factories.py` — TestTheFactoriesDoNotShareTheirDefaults: test_each_call_gets_its_own_copy_of_a_default, test_and_the (~646 tok)
- `test_metrics_endpoint.py` — MetricsTestCase: setUp, scrape, test_with_the_token_it_answers, test_without_a_token_configured_ther (~1607 tok)
- `test_migrations.py` — MigrationsTest: test_only_single_head_revision_in_migrations, test_every_migration_compiles, test_co (~3051 tok)
- `test_pools.py` — PoolTestCase: setUp, clear, test_a_data_source_gets_a_pool_of_its_own_by_default, test_two_sources_n (~3223 tok)

## tests/handlers/

- `test_kind_partition.py` — KindTestCase: setUp, ids, setUp, test_the_ordinary_list_leaves_the_streaming_ones_out + 23 more (~3519 tok)
- `test_mcp_languages.py` — TestTheToolsAboutSqlRefuseWhatIsNot: setUp, call, test_check_sql_does_not_report_findings_about_prom (~735 tok)
- `test_mcp.py` — McpTestCase: rpc, setUp, post, test_a_key_belonging_to_somebody_without_the_feature_is_refused + 29  (~41947 tok)
- `test_notebooks.py` — NotebookApiTestCase: setUp, a_notebook, a_cell, test_a_published_notebook_is_in_the_list + 20 more (~4567 tok)
- `test_permanent_delete.py` — PermanentDeleteTestCase: delete_query, delete_dashboard, test_it_goes, test_its_visualizations_and_t (~2260 tok)
- `test_queries.py` — TestQueryResourceGet: test_the_api_key_goes_only_to_people_who_may_regenerate_it, test_a_public_toke (~8302 tok)
- `test_widgets.py` — TestAnIdThatMatchesNothing: test_is_a_404_not_a_500, create_widget, test_create_widget, test_wont_cr (~994 tok)

## tests/mcp/

- `test_layout.py` — TestTheTableMatchesTheBrowser: declared_in_viz_lib, test_every_visualization_is_the_size_the_browser (~1606 tok)

## tests/models/

- `test_data_sources.py` — DataSourceTest: test_get_schema, test_get_schema_uses_cache, test_get_schema_skips_cache_with_refres (~2006 tok)

## tests/notebooks/

- `test_python_cells.py` — wires: columns, session_for, detach, ship + 15 more (~5839 tok)
- `test_run.py` — NotebookTestCase: result, answering, setUp, cell + 25 more (~3637 tok)
- `test_store.py` — StoreTestCase: columns, setUp, tearDown, declared_type + 25 more (~3325 tok)

## tests/query_runner/

- `test_prometheus.py` — TestPrometheus: setUp, test_get_instant_rows, test_get_range_rows, test_get_datetime_now + 7 more (~12538 tok)
- `test_query_language.py` — Source: test_sql_is_the_default, test_a_type_no_runner_claims_is_read_as_sql, test_prometheus_and_mi (~1547 tok)
- `test_runner_faults.py` — TestAnEncoderMayAnswerZero: test_a_zero_decimal_from_mongo_is_stored, test_and_any_encoder_answering (~1101 tok)

## tests/streams/

- `test_broker.py` — BrokerTestCase: broker_is_running, setUp, drop, produce + 19 more (~4783 tok)
- `test_decode_streams.py` — TestTheWindow: order, setUp, read_as_avro, test_avro_lands_with_columns_duckdb_typed_properly + 21 m (~3504 tok)
- `test_decode.py` — TestAvroSchemaFiles: avsc, proto, avro_bytes, parsed + 14 more (~8659 tok)

## tests/tasks/

- `test_notebook_cells.py` — CellJobTestCase: setUp, a_cell, test_a_sql_cell_takes_a_slot_and_gives_it_back, note + 8 more (~1710 tok)
- `test_schedule.py` — TestSchedule: tick, setUp, test_schedules_a_new_job, foo + 23 more (~2392 tok)

## viz-lib/src/visualizations/candlestick/

- `buildOption.ts` — [open, close, low, high] -- ECharts' order, not OHLC. (~1486 tok)

## viz-lib/src/visualizations/chart/

- `getOptions.ts` — DEFAULT_OPTIONS: getOptions (~1175 tok)
- `lineDash.ts` — How a line is drawn, so two series can be told apart without a second colour. (~615 tok)
- `panels.ts` — Stacked panels: several plots sharing one x axis. (~1438 tok)
- `rollup.ts` — What happens when several rows share an x. (~1106 tok)

## viz-lib/src/visualizations/chart/Editor/

- `DefaultColorsSettings.tsx` — DefaultColorsSettings — renders table (~1030 tok)
- `PanelSettings.test.tsx` — The Y-Axis tab, which is where the panel count and the per-panel rows live. (~1752 tok)
- `PanelSettings.tsx` — Whether this chart can be divided into panels. (~615 tok)
- `RollupSetting.test.tsx` — findByTestID (~790 tok)
- `SeriesSettings.tsx` — SortableBodyRow — renders table (~2313 tok)
- `ThresholdColorSettings.tsx` — Whether any part of this chart is drawn as bars. (~1223 tok)
- `YAxisSettings.tsx` — YAxisSettings (~1338 tok)

## viz-lib/src/visualizations/chart/echarts/

- `buildOption.axisRange.test.ts` — options: series, yAxes (~1222 tok)
- `buildOption.lineDash.test.ts` — series: options (~1406 tok)
- `buildOption.panels.test.ts` — series: options (~4650 tok)
- `buildOption.rollup.test.ts` — ROWS: series, drawn (~1698 tok)
- `buildOption.threshold.test.ts` — The measure out of a datum, whichever shape it is in. (~1862 tok)
- `buildOption.ts` — What ECharts asks for on a value axis when nobody tells it otherwise. (~11349 tok)
- `followCursor.ts` — A series' drawn position at the x under the pointer. (~1617 tok)
- `tooltipFocus.test.ts` — OPTIONS: items, chartWith (~2168 tok)

## viz-lib/src/visualizations/network/

- `buildOption.ts` — Everything through this node, which is what its size means. (~1928 tok)

## viz-lib/src/visualizations/parallel/

- `buildOption.ts` — How see-through to draw the lines. (~1525 tok)

## viz-lib/src/visualizations/sankey/

- `Editor.tsx` — Editor (~406 tok)

## viz-lib/src/visualizations/streamgraph/

- `buildOption.ts` — A point on the river: when, how much, and which band. (~1532 tok)

## viz-lib/src/visualizations/table/

- `cellFormat.test.tsx` — rules (~4082 tok)
- `cellFormat.ts` — Colour the cell behind the text, or the text itself. (~2072 tok)
- `renderer.less` — Styles: 7 rules (~1900 tok)
- `utils.tsx` — Min and max per column, over every row -- not just the visible page. (~3285 tok)

## viz-lib/src/visualizations/table/Editor/

- `CellFormatSection.tsx` — CellFormatSection (~1293 tok)

## viz-lib/src/visualizations/tree/

- `buildOption.ts` — ECharts wants one root. A query returns several top-level branches, so (~1440 tok)
