---
version: "alpha"
name: Geodata Workbench Quiet Field
description: A restrained interface system for dense geodata operations.
colors:
  primary: "#232823"
  secondary: "#66706a"
  accent: "#2f6f5e"
  accent-hover: "#25584b"
  accent-soft: "#e5eee9"
  info: "#315f7d"
  danger: "#9d3d36"
  warning: "#846327"
  background: "#f3f4f1"
  surface: "#ffffff"
  surface-muted: "#f7f8f5"
  border: "#d9ddd6"
  border-strong: "#b9c1b8"
typography:
  heading:
    fontFamily: IBM Plex Sans KR
    fontSize: 1.25rem
    fontWeight: 600
    lineHeight: 1.25
    letterSpacing: 0
  body:
    fontFamily: IBM Plex Sans KR
    fontSize: 0.875rem
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: 0
  label:
    fontFamily: IBM Plex Sans KR
    fontSize: 0.75rem
    fontWeight: 600
    lineHeight: 1.25
    letterSpacing: 0
rounded:
  xs: 4px
  sm: 6px
  md: 8px
spacing:
  xs: 4px
  sm: 8px
  md: 12px
  lg: 16px
components:
  panel:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.primary}"
    rounded: "{rounded.md}"
    padding: 16px
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.surface}"
    rounded: "{rounded.sm}"
    height: 36px
  button-primary-hover:
    backgroundColor: "{colors.accent-hover}"
    textColor: "{colors.surface}"
  table-header:
    backgroundColor: "{colors.surface-muted}"
    textColor: "{colors.secondary}"
  alert-info:
    backgroundColor: "{colors.info}"
    textColor: "{colors.surface}"
    rounded: "{rounded.sm}"
  alert-danger:
    backgroundColor: "{colors.danger}"
    textColor: "{colors.surface}"
    rounded: "{rounded.sm}"
  alert-warning:
    backgroundColor: "{colors.warning}"
    textColor: "{colors.surface}"
    rounded: "{rounded.sm}"
  alert-soft:
    backgroundColor: "{colors.accent-soft}"
    textColor: "{colors.primary}"
    rounded: "{rounded.sm}"
  divider:
    backgroundColor: "{colors.border}"
    textColor: "{colors.primary}"
    height: 1px
  selected-outline:
    backgroundColor: "{colors.border-strong}"
    textColor: "{colors.primary}"
    rounded: "{rounded.sm}"
---

## Overview
This dashboard is an operations surface, not a marketing page. The design should feel like a field notebook connected to a database console: plain, durable, readable, and calm under repeated use.

## Colors
Use neutral surfaces with a muted green accent for the main action path. Reserve blue for map/data information, rust red for destructive states, and amber only for warnings. Avoid gradients, saturated blues, glowing shadows, decorative badges, and candy-like pills.

## Typography
Keep IBM Plex Sans KR for Korean readability. Use compact headings inside panels, 12px labels for controls, and 11-12px table text where density matters. Letter spacing stays at 0.

## Layout
Preserve the existing dashboard structure: header, segmented tabs, stacked work panels, and the browse split between table preview and map. Panels use a single-pixel border, 8px radius, and no decorative background effects.

## Elevation & Depth
Depth is functional only. Use borders and subtle interaction states instead of heavy shadows. Modals may use a single soft shadow because they sit above the workspace.

## Shapes
Default radius is 6px for controls and 8px for panels. Avoid pill-shaped controls except where the browser or map vendor UI already supplies them.

## Components
Buttons are compact and direct. Primary buttons use the muted green accent. Tables use sticky, flat headers and clear row separators. Empty states use dashed borders only when they mark a missing selection or absent data.

## Do's and Don'ts
Do keep data visible, controls predictable, and state colors restrained.
Do not add animated orbs, glossy gradients, large hero treatments, emoji icons, or decorative workflow cards.
