from .registry import BackgroundSpec, Theme

THEME = Theme(
    name="cinematic_dark",
    description="Deep charcoal-blue background, white text with dark outline, golden active word.",
    font_candidates=("Montserrat-Bold", "Poppins-Bold", "Inter-Bold", "DejaVuSans-Bold"),
    font_size_frac=0.105,
    min_font_size_frac=0.06,
    fill=(250, 248, 244),
    accent=(255, 196, 61),
    outline=(8, 10, 16),
    outline_frac=0.10,
    shadow_color=(0, 0, 0, 170),
    shadow_offset_frac=(0.0, 0.06),
    shadow_blur_frac=0.05,
    shadow_extra_frac=0.02,
    line_spacing=1.14,
    default_entrance="fade",
    background=BackgroundSpec(
        style="gradient", top=(26, 32, 48), bottom=(8, 10, 18), light=(70, 86, 120),
        light_strength=0.35, light_center=(0.5, 0.35), vignette=0.35, texture=0.008,
        breathe=0.02, breathe_period=11.0,
    ),
)
