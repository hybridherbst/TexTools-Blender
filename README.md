> ⚠️ Unofficial community fork — Blender 5 compatibility and maintenance.

This repository is an **unofficial, community-maintained fork** of the original
[TexTools for Blender](https://github.com/franMarz/TexTools-Blender), created
solely to keep the add-on working on newer Blender versions (5.x) and to fix
blocking issues.

All credit for TexTools’ design, features, and workflow belongs to the original
authors and contributors. If the upstream project becomes active again, I’d be
happy to contribute changes back or retire this fork in favor of the original.

# TexTools for Blender #

TexTools is a free addon for Blender with a set of professional UV and Texture tools. Fully compatible with Blender 3.2 and later, most features should work for Blender versions as old as 2.8, including: UV Layout tools (Align, Rectify, Sort, Randomize...), multiple out-of-the-box Texture Baking modes, Texel Density tools, smart UV Selection operators, Color ID tools and some UV related Mesh creation utilities.

Back in 2009, @renderhjs released the [Original TexTools](http://renderhjs.net/textools/) for 3DS MAX, and later, the Blender add-on, which was discontinued from the 2.79 Blender version until @SavMartin ported it to the 2.8 Blender release.

## Installation ##

1. Download TexTools for Blender from [master](https://github.com/franMarz/TexTools-Blender/archive/refs/heads/master.zip)(best), or the latest release.
2. In Blender from the **File** menu open **User Preferences** ![](http://renderhjs.net/textools/blender/img/installation_open_preferences.png) 
3. Go to the **Add-ons** tab ![](http://renderhjs.net/textools/blender/img/installation_addons.png).
4. Look for any old version of TexTools currently installed and uninstall it.
5. Hit **Install Addon-on from File...** ![](http://renderhjs.net/textools/blender/img/installation_install_addon_from_file.png) and Select the zip file.
6. Enable the TexTools Addon.
7. The TexTools panel can be found in the **UV/Image Editor** view ![](http://renderhjs.net/textools/blender/img/installation_uv_image_editor.png) in the left side Panel.

## Links ##
* Blenderartists [discussion thread](https://blenderartists.org/forum/showthread.php?443182-TexTools-for-Blender)
* Original author [renderhjs.net](http://www.renderhjs.net/) personal website, all written in haxe ;)
* renderhjs's [Git repository](https://bitbucket.org/renderhjs/textools-blender) on BitBucket
* renderhjs's [release log](http://renderhjs.net/textools/blender/log.html)
* renderhjs's [3dsMax version](http://renderhjs.net/textools/) of TexTools
* Polycount [discussion thread](http://polycount.com/discussion/197226/textools-for-blender)

## Documentation ##
Visit the [Official Website & Documentation](http://renderhjs.net/textools/blender/) for an in depth overview of the original tools (outdated)

### UV straightening tools

- **Straight** straightens one open UV edge chain, temporarily pins it, and relaxes the surrounding island.
- **Grid Straight** makes every selected grid row and column horizontal or vertical while retaining their existing distribution.
- **Grid Relax** solves each connected grid independently and jointly redistributes rows and columns to minimize per-face 3D aspect error. **Movable Boundary** defaults to **Auto (Least Straight)** so an incompatible AABB cannot force stretch across every panel; choose **Fixed AABB** explicitly to lock all four bounds.
- **Rectify** rebuilds selected quad faces as a rectangular Follow Active Quads layout.
- **Iron Faces** unwraps the selected faces while preserving their exact original UV AABB and stabilizing the result against arbitrary unwrap rotation. **Align to Axes** snaps a clear dominant direction horizontally or vertically while leaving near-radial shapes unsnapped.
- UV Sync is supported by Relax, Straight, Align Edge, Stitch, Unwrap, and Split Bevel; synchronized mesh component selections are translated temporarily without changing the original mesh selection.
