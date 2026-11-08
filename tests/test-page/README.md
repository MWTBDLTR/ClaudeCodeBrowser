# ClaudeCodeBrowser feature test page

A local page that exercises every MCP tool the extension exposes.

```bash
python tests/test-page/serve.py        # http://localhost:8899/
```

Open `http://localhost:8899/` in the browser with the extension loaded, then drive it
with the `browser_*` tools. Every interaction that reaches the page is recorded in
`window.__ccb.events` and ticks the checklist in the right-hand panel.
`__ccb.missing()` lists the checks that haven't fired yet.

Notes:
- Don't use port 8765: the extension's own bridge server listens there.
- `browser_execute_script` runs in the extension's isolated content-script world, so
  page globals like `window.__ccb` aren't visible from it. Read the checklist from the
  DOM instead: `[...document.querySelectorAll('#checklist li.pass')].map(l => l.id.slice(4))`.
- Each check should fire **once** per action. A doubled entry in the event log means
  a tool dispatched the event twice.
- `browser_request_approval` and the solve step of `browser_solve_captcha` need a
  person at the browser to click Approve/Deny or tick the mock captcha.

| Section | Tools exercised |
| --- | --- |
| 1. Clicking | `browser_click` (selector, text, XPath, x/y, double, right) |
| 2. Typing | `browser_type` (id, name, placeholder, clear, press_enter, textarea, contenteditable); password guard |
| 3. Form values | `browser_get_value`, `browser_set_value`, `browser_select_option`, checkbox/radio/range/date |
| 4. Hover & keys | `browser_hover`, `browser_press_key` (+ modifiers), `browser_click_and_wait` (modal) |
| 5. Dynamic | `browser_wait_for_element`, `browser_wait_for_change`, `browser_wait_and_act`, `browser_observe_element` / `browser_stop_observing`, `browser_inject_observer` |
| 6. Network & console | `browser_start_logging` / `stop` / `clear`, `browser_get_console_logs`, `browser_get_network_logs`, `browser_wait_for_network_idle` |
| 7. Scrolling | `browser_scroll` (page, element, to_element, bottom), `browser_scroll_and_capture` |
| 8. Navigation & tabs | `browser_navigate`, `browser_go_back` / `forward`, `browser_refresh`, `browser_hard_refresh`, `browser_reload_by_url`, `browser_reload_all`, tab tools |
| 9. Audit fodder | `browser_audit_page` (missing alt, unlabeled input, empty link/button, skipped heading) |
| 10. Captcha | `browser_solve_captcha` against a local mock Turnstile widget (a human ticks the box) |
| 11. Tall area | full-page `browser_screenshot`, `browser_scroll_and_capture` |
| Anywhere | `browser_execute_script`, `browser_eval_chain`, `browser_highlight`, `browser_get_text`, `browser_get_elements`, `browser_get_page_info`, `browser_request_approval`, `browser_run_workflow`, `browser_safety_status` |
