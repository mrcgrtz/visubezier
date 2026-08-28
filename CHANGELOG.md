# Changelog

All notable changes to VisuBezier will be documented in this file.

## 2.0.0 - 2026-08-28

First release of the Sublime Text package, ported from the VS Code extension.
Everything below 2.0.0 describes the VS Code extension this was forked from.

### Added

-   Numeric evaluation of every supported easing, so `linear()` now animates
    correctly. The VS Code extension could only draw it, because its renderer
    had no `linear()` support.
-   Pure-Python PNG and GIF encoders and a small anti-aliased rasteriser,
    since minihtml renders neither SVG nor CSS animation.
-   Animation by swapping the preview image with `update_popup` on a timer.
    minihtml supports no CSS animation, and paints only the first frame of an
    animated GIF, so the animation has to be driven by the plugin. The GIF
    encoder is kept for generating the README asset via
    `tools/make_preview.py`.
-   An `animate` setting. When `false`, the preview is a static strobe of the
    motion rather than a GIF: faster to render and far smaller.
-   A test suite runnable outside Sublime Text with `python3 tests/run.py`.

### Changed

-   Settings are renamed to Sublime conventions, and languages become scope
    selectors:

    | VS Code | Sublime Text |
    | --- | --- |
    | `visubezier.defaulteasingfunction` | `reference_easing_function` |
    | `visubezier.defaultduration` | `duration` |
    | `visubezier.defaultbackground` | `background` |
    | `visubezier.defaultcolor` | `foreground` |
    | `visubezier.defaultlanguages` | `selectors` |

-   `linear()` stop positions are forced to be non-decreasing, per the CSS
    Easing Level 2 spec, and a trailing stop keeps its own value rather than
    being snapped to `1`.
-   Matches are marked with an underline rather than an inline icon, which
    minihtml cannot place inside a line of text.

### Fixed

-   Submodules under `core/` are reloaded along with the top-level plugin.
    Sublime caches modules in subdirectories, so an updated `core/` would
    otherwise keep running the previously imported copy until a restart.
-   Easings that overshoot no longer escape the preview area.
-   Adjacent easings are both detected. The upstream pattern consumed the
    delimiter following a match, so the second of `ease,ease` was missed.
-   The `cubic-bezier()` and `linear()` patterns no longer match empty
    arguments such as `cubic-bezier(,,,)`.

### 1.6.1 - 2023-09-02

-   Fixed parsing of `linear()` with negative values, and rendering of `linear()` with a value greater than `1` which was previously clamped to `1`.

### 1.6.0 - 2023-03-19

-   Added support for [`linear()` syntax](https://jakearchibald.github.io/csswg-drafts/css-easing-2/Overview.html#the-linear-easing-function) easing functions. Animation preview is not yet implemented in VS Code, but the SVG graph is correctly depicted (based on my interpretation of the spec, which I hope to be correct).
-   Added a licence file.
-   Updated the underlying VS Code Extension required files to run with more modern code (Node 18, TypeScript 5, VS Code 1.76+, and other things I hardly understand).
-   Updated the extension's package to patch vulnerabilities.

### [1.5.0] - 2022-12-01

### Added

-   Added a `defaultlanguages` configuration option to only run the extension in relevant languages, overridable by the user if needed. (thanks to [@robole](https://github.com/robole) for the suggestion and to [tjx666](https://github.com/tjx666) for the example file!).

### Changed

-   Patched a few package vulnerabilities.
-   Cleaned up the extension's codebase to a small extent.

## [1.4.0] - 2021-05-20

### Added

-   Support for `steps()` and `step-start`/`step-end` syntax.

### Changed

-   Solid underline changed to a dotted underline.
-   Comments/typings updated.

## [1.3.5] - 2021-05-03

### Changed

-   Patch the security vulnerabilities for `url-parse`.

## [1.3.4] - 2020-07-27

### Added

-   Added an icon before the timing functions that can be previewed.

## [1.3.2] - 2020-07-27

### Changed

-   Fixed the `ease` mapping and allow to detect more than one function per declaration.

## [1.3.1] - 2020-05-02

### Changed

-   Patch the security vulnerabilities for `minimist`.

## [1.3.0] - 2020-05-02

### Changed

-   Fixed some greed in the detection regular expression.

## [1.2.0] - 2020-02-17

### Changed

-   Updated icon
-   Updated extension name
-   Patch the security vulnerabilities for `braces`, `js-yaml` and `fstream`.

## [1.1.2] - 2019-05-03

### Changed

-   Patch the security vulnerabilities for `tar` and `node.extend`.

## [1.1.1] - 2018-09-15

### Changed

-   Improve the regular expression to be less greedy and not detect words like "release".

## [1.1.0] - 2018-09-07

### Added

-   Add a preview of the Bézier curve next to the animation.
-   Add options to customize the foreground and background colors of the animation preview.

### Changed

-   Improve the readability of the SVG markup by separating the values into variables.
-   Change the styling of preview-capable functions from `cursor: crosshair` to `text-decoration: underline`.
