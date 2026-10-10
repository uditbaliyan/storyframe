from .registry import BackgroundSpec, Theme

THEME = Theme(
    name="english_pink_story",
    description="Soft pastel pink background, huge black text, thick white outline, warm coral active word.",
    font_candidates=("Montserrat-ExtraBold", "Poppins-ExtraBold", "Poppins-Bold", "Inter-ExtraBold", "DejaVuSans-Bold"),
    font_size_frac=0.14,
    min_font_size_frac=0.07,
    fill=(22, 16, 24),
    accent=(255, 92, 72),
    outline=(255, 255, 255),
    outline_frac=0.115,
    shadow_color=(70, 20, 50, 150),
    shadow_offset_frac=(0.0, 0.05),
    shadow_blur_frac=0.035,
    shadow_extra_frac=0.025,
    line_spacing=1.12,
    box_width_frac=0.88,
    box_height_frac=0.55,
    max_lines=3,
    default_entrance="slide_up",
    background=BackgroundSpec(
        style="gradient", top=(255, 224, 234), bottom=(247, 178, 205), light=(255, 246, 250),
        light_strength=0.40, light_center=(0.5, 0.40), vignette=0.07, texture=0.010,
        breathe=0.012, breathe_period=9.0,
    ),
)
