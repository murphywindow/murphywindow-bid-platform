# Murphy Window UI Visual System

This document defines the live application’s visual contract. The system is dense, restrained, and estimator-oriented: the shell establishes the visual language, tables extend it, and commercial data remains the focus. Visual preferences must never mutate project data, create audit events, or change bid versions.

## Principles

- Use one visual authority: the `--ui-*`, `--table-*`, spacing, radius, control, layout, motion, and z-index variables in `app/static/styles.css`.
- Older variable names are compatibility aliases only. New rules must use the authoritative tokens.
- Prefer a single section boundary and a contained table wrapper. Avoid nested borders of equal strength.
- Keep ordinary rows at 28px and controls compact. Wide estimating tables scroll inside their wrapper rather than compressing columns.
- Use serif type only for major page titles and established commercial summary figures. Interface text uses the system sans stack.
- Preserve all semantic table markup, keyboard behavior, sorting, controlled-value workflows, Base/Alternate behavior, autosave focus, and scroll restoration.

## Exact tokens

```css
:root {
  --ui-canvas: #f3f6f4;
  --ui-sidebar: #eef3f0;
  --ui-surface: #ffffff;
  --ui-surface-subtle: #f8faf9;
  --ui-surface-muted: #f2f6f4;
  --ui-surface-strong: #e8f0ec;

  --ui-brand: #244f41;
  --ui-brand-hover: #1d4236;
  --ui-brand-active: #17372d;
  --ui-brand-soft: #e8f1ed;
  --ui-brand-soft-hover: #dcebe4;

  --ui-text: #18241f;
  --ui-text-secondary: #4f6058;
  --ui-text-muted: #718078;
  --ui-text-faint: #8c9992;
  --ui-text-on-brand: #ffffff;

  --ui-border: #d4ded9;
  --ui-border-subtle: #e4ebe7;
  --ui-border-strong: #b8c7bf;
  --ui-divider: #dde5e1;

  --ui-success: #2f6a4d;
  --ui-success-bg: #ebf5ef;
  --ui-warning: #936000;
  --ui-warning-bg: #fff6df;
  --ui-error: #9b3b3b;
  --ui-error-bg: #fdf0f0;
  --ui-info: #356579;
  --ui-info-bg: #edf5f8;

  --table-header-bg: #eef3f0;
  --table-header-hover: #e5eee9;
  --table-editable-bg: #fffdf7;
  --table-editable-hover: #fffaf0;
  --table-calculated-bg: #f3f7f5;
  --table-readonly-bg: #f6f8f7;
  --table-row-hover: #f4f8f6;
  --table-row-selected: #eaf3ef;
  --table-subtotal-bg: #e7efeb;
  --table-total-bg: #dce9e3;

  --space-1: 2px;
  --space-2: 4px;
  --space-3: 6px;
  --space-4: 8px;
  --space-5: 12px;
  --space-6: 16px;
  --space-7: 20px;
  --space-8: 24px;
  --space-9: 32px;

  --radius-xs: 3px;
  --radius-sm: 4px;
  --radius-md: 6px;
  --radius-lg: 8px;
  --radius-pill: 999px;

  --shadow-subtle: 0 1px 2px rgba(18, 43, 34, 0.07);
  --shadow-floating: 0 6px 18px rgba(18, 43, 34, 0.13);
  --focus-ring: 0 0 0 2px rgba(36, 79, 65, 0.22);
  --focus-border: #2b6753;

  --topbar-height: 52px;
  --sidebar-width: 206px;
  --workspace-padding-x: 18px;
  --workspace-padding-top: 12px;
  --workspace-padding-bottom: 24px;

  --control-height-compact: 26px;
  --control-height-default: 30px;
  --control-height-large: 34px;
  --table-header-height: 28px;
  --table-row-height: 28px;
  --table-subtotal-height: 30px;
  --table-cell-padding-x: 7px;
  --table-cell-padding-y: 4px;

  --motion-fast: 90ms;
  --motion-normal: 130ms;
  --z-base: 1;
  --z-sticky-cell: 12;
  --z-sticky-header: 20;
  --z-sidebar: 40;
  --z-topbar: 50;
  --z-popover: 100;
  --z-dialog: 200;
}
```

## Typography

The interface stack is `-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif`. Major page titles use Georgia at 27/30px and weight 700. Top-bar identity is 14/17px at 650; secondary top-bar text and page eyebrows are 9.5/12px. Page descriptions are 11.5/16px. Section titles are 13/17px at 650 and helper text is 10.5/14px.

Table headers use 10.5/13px at 650. Table bodies use 11.5/16px at 400, calculated values use weight 550, and subtotals use weight 650. Numeric values use tabular lining figures. Frame summary labels are 8.5/10px uppercase; values retain the established serif commercial treatment at 14/17px and weight 700.

## Layout and controls

- Top bar: 52px high, 14px horizontal padding, 12px item gap, 28px logo, no blur or large shadow.
- Sidebar: 206px wide with 10px vertical and 8px horizontal padding. Search is 32px high; navigation rows are 30px.
- Workspace: fluid width with 12px top, 18px horizontal, and 24px bottom padding.
- Project toolbar: 42px high with 5px × 6px padding and an 8px lower gap.
- Buttons: compact 26px/8px, default 30px/10px, and large 34px/12px. All use a 5px radius and a 5px icon gap.
- Frame scenario tabs: 30px container and 24px tab controls. The scenario index bar is 30px high.

## Tables and states

Shared live tables use separate borders, zero spacing, fixed layout, 28px headers and rows, and 4px × 7px cells. Wide tables use `width: max-content` with a 100% minimum; compact secondary tables stop at their content width. Header labels remain horizontal and may wrap to two lines only where needed.

In-cell controls are 24px high with 2px × 5px padding, a transparent border, optional subtle bottom cue, and a 3px radius. Hover uses `--table-editable-hover`; focus uses white, `--focus-border`, and `--focus-ring` without changing row height.

- Editable: warm `--table-editable-bg` cue.
- Calculated/read-only: `--table-calculated-bg`, secondary text, weight 550.
- Inherited: `--table-readonly-bg`.
- Saved override: warning background and a restrained 3px left marker; Revert remains available.
- Pending or warning: `--ui-warning-bg` with the appropriate status indicator.
- Invalid: `--ui-error-bg` and `--ui-error` border.
- Selected: `--table-row-selected`.
- Subtotal/total: 30px subtotal row using `--table-subtotal-bg`; grand totals use `--table-total-bg`.

Action columns are 54px by default and sticky where appropriate. Direct icon actions have 26px hit areas, a 4px radius, brand-soft hover, and error-colored destructive hover. Focus and hover must not move or resize controls.

## Frame Takeoff

The desktop section header is an exact eight-column grid: `26px 96px minmax(260px, 1fr) 72px 108px 88px 70px 30px`. It is at least 66px high. The Cost Code selector shows only the normalized code; its full description is adjacent and available by tooltip. SF, Installation Materials, Sell $/SF, History, and actions align in fixed cells. Sell $/SF uses the Cost Code Bid summary, including the selected Quote and every other included Bid component, so it matches History’s current-value metric.

Frame Lines use an intentional 1750px worksheet width inside a horizontally scrolling wrapper. Default columns are 86, 58, 74, 72, 72, 64, 74, 82, 76, 80, 112, 96, 112, 96, 128, 112, 180, 122, and 54px. Mark and Qty remain sticky left; actions remain sticky right with a one-pixel boundary.

Base Installation Materials is a compact 762px table. Its columns are 220, 130, 98, 128, 118, and 68px. It stays left aligned and deliberately leaves unbordered space to the right. Add Frame and Add Material remain below their tables at the lower left.

## Responsive and accessibility expectations

At the medium breakpoint, the Frame identity occupies the first row and its four commercial summary cells occupy a second row. At the narrow breakpoint, the sidebar follows the existing drawer behavior, top-bar identity compresses, table wrappers keep local horizontal scrolling, and scenario tabs remain one line with local overflow.

Every interactive control needs a visible keyboard focus state and an accessible name. Truncated project, section, and Cost Code values expose their full value through `title`/tooltip behavior. Status must not rely on color alone. Reduced-motion preferences remain honored. Tooltips and popovers use the shared floating shadow and must not be clipped by table wrappers.

## Usage examples

Correct:

- Use `var(--ui-border)` for a card or table perimeter and `var(--ui-border-subtle)` for row dividers.
- Use a 26px compact button in a table toolbar and a 30px default button in a page toolbar.
- Let a wide table scroll in `.table-wrap`; keep the page itself free of horizontal overflow.
- Preserve semantic `<table>`, `<th scope="col">`, output, validation, and data-hook markup.

Incorrect:

- Adding a one-off green, spacing value, radius, or shadow when a shared token applies.
- Stretching a six-column compact table across the entire workspace.
- Expanding a textarea merely because it received focus.
- Making all calculated values bold, centering currency, rotating headers, or using heavy borders around every cell.
- Storing column widths, focus, hover, or scroll state in commercial project JSON.
