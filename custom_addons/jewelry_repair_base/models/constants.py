"""Shared selection constants for jewelry models."""

GEM_ORIGIN = [
    ("natural", "Natural"),
    ("lab_grown", "Laboratory Grown"),
]

GEM_CUT_SHAPES = [
    ("round", "Round"),
    ("oval", "Oval"),
    ("princess", "Princess"),
    ("cushion", "Cushion"),
    ("emerald", "Emerald"),
    ("radiant", "Radiant"),
    ("pear", "Pear"),
    ("marquise", "Marquise"),
    ("heart", "Heart"),
    ("asscher", "Asscher"),
    ("trapezoid", "Trapezoid"),
]

STANDARD_ROUND_BRILLIANT_SIZES = [
    # Small melee (standard industry values)
    (0.8, 0.0015), (0.9, 0.0025), (1.0, 0.005), (1.1, 0.006),
    (1.15, 0.007), (1.2, 0.008), (1.25, 0.009), (1.3, 0.010),
    (1.35, 0.011), (1.4, 0.012), (1.45, 0.013), (1.5, 0.015),
    (1.6, 0.018), (1.7, 0.020), (1.75, 0.025), (1.8, 0.027),
    (1.9, 0.030), (2.0, 0.030), (2.1, 0.040), (2.2, 0.040),
    (2.25, 0.045), (2.3, 0.050), (2.4, 0.055), (2.5, 0.060),
    (2.6, 0.065), (2.7, 0.070), (2.75, 0.080), (2.8, 0.080),
    (2.9, 0.090), (3.0, 0.100), (3.1, 0.110), (3.2, 0.120),
    (3.25, 0.130), (3.3, 0.130), (3.4, 0.140), (3.5, 0.150),
    (3.6, 0.170), (3.7, 0.180), (3.75, 0.190), (3.8, 0.200),
    (3.9, 0.220), (4.0, 0.250),
    # Larger stones (midpoints from standard chart)
    (4.3, 0.300), (4.475, 0.330), (4.675, 0.400), (4.775, 0.430),
    (5.0, 0.500), (5.05, 0.530), (5.275, 0.600), (5.6, 0.700),
    (5.8, 0.800), (6.0, 0.900), (6.35, 1.000), (6.75, 1.250),
    (7.25, 1.500), (7.65, 1.750), (8.05, 2.000), (8.65, 2.500),
    (9.05, 3.000), (9.55, 3.500), (10.05, 4.000), (10.55, 4.500),
    (11.05, 5.000), (11.55, 6.000), (12.05, 7.000), (12.55, 8.000),
    (12.95, 9.000), (13.40, 10.000), (14.15, 12.000), (15.90, 15.000),
    (17.65, 20.000),
]

GEM_LABS = [
    ("gia", "GIA"),
    ("igi", "IGI"),
    ("hrd", "HRD"),
    ("ags", "AGS"),
    ("egl", "EGL"),
    ("cibjo", "CIBJO"),
    ("other", "Other"),
]

GRADE_QUALITY = [
    ("excellent", "Excellent"),
    ("very_good", "Very Good"),
    ("good", "Good"),
    ("fair", "Fair"),
    ("poor", "Poor"),
]

GEM_FLUORESCENCE = [
    ("none", "None"),
    ("faint", "Faint"),
    ("medium", "Medium"),
    ("strong", "Strong"),
    ("very_strong", "Very Strong"),
]
