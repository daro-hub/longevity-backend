"""Every numeric constant used by the domain engine, plus its citation.

This module exists so the engine is auditable rather than "trust me": every
constant exported here must have a matching entry in ``REFERENCES``, and
``tests/domain/test_references.py`` enforces that mechanically — a new magic
number with no citation fails CI. ``GET /v1/references`` exposes this
registry so the numbers are publicly inspectable.

Two explicit conventions used everywhere else in the domain package (macros,
food DB, validator) are recorded here so there is exactly one place to look:

1. **Atwater identity.** Fiber's ~2 kcal/g is deliberately ignored; fiber is
   treated as a subset of carbohydrates. This keeps ``4*P + 4*C + 9*F == kcal``
   exactly true everywhere — targets, food DB rows, and the plan validator.
2. **Activity multipliers are the Harris-Benedict-era 5-band convention, NOT
   the FAO/WHO/UNU 2004 PAL bands** (which are 1.40-1.69 / 1.70-1.99 /
   2.00-2.40 and use a 3-band scale). Do not cite FAO for these numbers.
   TDEE from any such multiplier is an estimate, typically accurate to
   roughly +/-10-15% for an individual — this must be surfaced in the UI,
   not just in this comment.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.enums import ActivityLevel, Goal, Sex


@dataclass(frozen=True)
class Reference:
    citation: str
    url: str | None = None
    note: str = ""


# ---------------------------------------------------------------------------
# Anthropometry
# ---------------------------------------------------------------------------

IBW_HEIGHT_THRESHOLD_CM = 152.4  # 5 ft; Devine formula base height
IBW_BASE_KG_MALE = 50.0
IBW_BASE_KG_FEMALE = 45.5
IBW_PER_INCH_OVER_KG = 2.3
CM_PER_INCH = 2.54

ADJUSTED_BW_FACTOR = 0.25  # ABW = IBW + factor * (actual - IBW), used when BMI >= 30

BMI_SEVERE_UNDERWEIGHT_MAX = 17.0
BMI_UNDERWEIGHT_MAX = 18.5
BMI_NORMAL_MAX = 25.0
BMI_OVERWEIGHT_MAX = 30.0
BMI_OBESE_I_MAX = 35.0
BMI_OBESE_II_MAX = 40.0
# >= BMI_OBESE_II_MAX is class III

# ---------------------------------------------------------------------------
# Energy — Mifflin-St Jeor BMR
# ---------------------------------------------------------------------------

MSJ_WEIGHT_COEF = 10.0
MSJ_HEIGHT_COEF = 6.25
MSJ_AGE_COEF = 5.0
MSJ_SEX_CONST_MALE = 5.0
MSJ_SEX_CONST_FEMALE = -161.0

ACTIVITY_MULTIPLIERS: dict[ActivityLevel, float] = {
    ActivityLevel.SEDENTARY: 1.2,
    ActivityLevel.LIGHT: 1.375,
    ActivityLevel.MODERATE: 1.55,
    ActivityLevel.ACTIVE: 1.725,
    ActivityLevel.VERY_ACTIVE: 1.9,
}

GOAL_TDEE_ADJUSTMENT: dict[Goal, float] = {
    Goal.LOSE_WEIGHT: -0.20,
    Goal.MAINTAIN: 0.0,
    Goal.GAIN_MUSCLE: 0.10,
}

# Calorie floors: the higher of the two applies.
BMR_RELATIVE_FLOOR_FACTOR = 1.1  # never go below 1.1x BMR
ABSOLUTE_CALORIE_FLOOR: dict[Sex, float] = {
    Sex.FEMALE: 1200.0,
    Sex.MALE: 1500.0,
}

# When protein/fat floors make the calorie target infeasible, relax the
# deficit in these steps (toward 0) before giving up.
DEFICIT_RELAXATION_STEPS = (0.20, 0.15, 0.10, 0.05, 0.0)

TDEE_UNCERTAINTY_PCT = 0.125  # midpoint of the commonly cited +/-10-15% band

# ---------------------------------------------------------------------------
# Macros
# ---------------------------------------------------------------------------

PROTEIN_G_PER_KG: dict[Goal, float] = {
    Goal.MAINTAIN: 1.2,
    Goal.LOSE_WEIGHT: 1.6,
    Goal.GAIN_MUSCLE: 1.8,
}
PROTEIN_G_PER_KG_ELDERLY_MIN = 1.2  # floor applied when age >= 65
PROTEIN_ELDERLY_AGE_THRESHOLD = 65
PROTEIN_G_PER_KG_MAX = 2.2  # hard cap regardless of goal

FAT_G_PER_KG_MIN = 0.8
FAT_KCAL_PCT_MIN = 0.20
FAT_KCAL_PCT_MAX = 0.35

KCAL_PER_G_PROTEIN = 4.0
KCAL_PER_G_CARB = 4.0
KCAL_PER_G_FAT = 9.0

FIBER_G_PER_1000KCAL = 14.0
FIBER_G_MIN = 25.0

HYDRATION_ML_PER_KG = 35.0
HYDRATION_ML_MIN = 1500.0
HYDRATION_ML_MAX = 4000.0
HYDRATION_ML_VERY_ACTIVE_BONUS = 500.0

# ---------------------------------------------------------------------------
# Guardrails
# ---------------------------------------------------------------------------

AGE_CHILD_MAX = 13  # < 13 refused entirely
AGE_MINOR_MAX = 18  # 13 <= age < 18: Q&A only, no computed plan
AGE_ELDERLY_MIN = 90  # 90 <= age <= AGE_IMPLAUSIBLE_MIN: warn
AGE_IMPLAUSIBLE_MIN = 100  # > 100 refused

HEIGHT_CM_MIN = 100.0
HEIGHT_CM_MAX = 250.0
WEIGHT_KG_MIN = 30.0
WEIGHT_KG_MAX = 300.0

BMI_UNDERWEIGHT_DEFICIT_BLOCK_MAX = 20.0  # lose_weight forced to maintain below this BMI
BMI_CLASS_III_MAX_DEFICIT_PCT = 0.15  # deficit capped at 15% for BMI >= 40

CONDITION_SCREEN_KEYWORDS = (
    "incinta",
    "pregnant",
    "gravidanza",
    "allattamento",
    "breastfeeding",
    "diabet",
    "renale",
    "kidney",
    "dialisi",
    "dialysis",
    "anoress",
    "anorex",
    "bulim",
    "eating disorder",
    "oncolog",
    "chemio",
    "chemo",
    "bariatric",
    "warfarin",
)

# ---------------------------------------------------------------------------
# Retrieval (frozen empirically once a corpus + eval set exist — see
# scripts/tune_threshold.py. Placeholder until then, deliberately generous.)
# ---------------------------------------------------------------------------

RETRIEVAL_MIN_SCORE = 0.40
RETRIEVAL_TOP_K = 8
RETRIEVAL_KEEP_ABOVE_THRESHOLD = 4

# ---------------------------------------------------------------------------
# Plan validation tolerances
# ---------------------------------------------------------------------------

KCAL_TOLERANCE_PCT = 0.05
KCAL_TOLERANCE_MIN_ABS = 75.0
PROTEIN_TOLERANCE_UNDER_PCT = 0.05
PROTEIN_TOLERANCE_OVER_PCT = 0.25
FAT_TOLERANCE_PCT = 0.15
CARB_TOLERANCE_PCT = 0.15
FIBER_TOLERANCE_MIN_FRACTION = 0.90  # fiber must reach >= 90% of target, no ceiling

PLAN_ITEM_GRAMS_MIN = 1.0
PLAN_ITEM_GRAMS_MAX = 1000.0
PLAN_MEAL_GRAMS_MAX = 2000.0

FIT_SCALE_MIN = 0.75
FIT_SCALE_MAX = 1.25
FIT_MAX_GREEDY_ITERATIONS = 10

FOOD_DB_ATWATER_TOLERANCE_PCT = 0.10

# ---------------------------------------------------------------------------
# Reference registry
# ---------------------------------------------------------------------------

MIFFLIN = Reference(
    citation="Mifflin MD, St Jeor ST, Hill LA, et al. A new predictive equation "
    "for resting energy expenditure in healthy individuals. "
    "Am J Clin Nutr. 1990;51(2):241-247.",
    note="BMR formula. Validated in healthy adults; not validated for "
    "pediatric/adolescent growth, hence AGE_MINOR routes around it.",
)

HARRIS_BENEDICT_ACTIVITY = Reference(
    citation="Commonly used activity-multiplier convention popularized "
    "alongside Harris-Benedict/Mifflin-St Jeor equations "
    "(sedentary 1.2 .. very active 1.9).",
    note="NOT the FAO/WHO/UNU 2004 PAL bands (1.40-1.69 / 1.70-1.99 / "
    "2.00-2.40, 3-band scale). Do not attribute these five numbers to FAO. "
    "TDEE derived from any such multiplier is an estimate, commonly cited "
    "as accurate to roughly +/-10-15% for a given individual.",
)

GOAL_ADJUSTMENT = Reference(
    citation="Conventional deficit/surplus sizing: ~20% deficit for weight "
    "loss, ~10% surplus for lean gain, commonly recommended to balance "
    "rate of change against muscle/metabolic preservation.",
    note="No single RCT source; this is a widely used practical convention, "
    "not a specific trial result.",
)

CALORIE_FLOORS = Reference(
    citation="Conventional safe-minimum-intake floors used in clinical "
    "weight-management guidance (commonly ~1200 kcal/day for women, "
    "~1500 kcal/day for men) to avoid severe underfeeding.",
    note="Practical floor, not itself the primary limiter — the "
    "BMR_RELATIVE_FLOOR_FACTOR (1.1x BMR) is the mechanism engaged first.",
)

DEVINE_IBW = Reference(
    citation="Devine BJ. Gentamicin therapy. Drug Intell Clin Pharm. "
    "1974;8:650-655.",
    note="Ideal body weight formula; widely reused for adjusted body weight "
    "in obesity-related dosing/nutrition calculations.",
)

ADJUSTED_BW = Reference(
    citation="Adjusted body weight = IBW + 0.25 * (actual weight - IBW), "
    "a common convention for protein/energy dosing in individuals with "
    "obesity, avoiding both underestimation (using IBW alone) and "
    "overestimation (using actual weight alone).",
)

WHO_BMI_CATEGORIES = Reference(
    citation="World Health Organization. Body mass index (BMI) "
    "classification.",
    url="https://www.who.int/europe/news-room/fact-sheets/item/a-healthy-lifestyle---who-recommendations",
    note="Standard adult BMI cut-points: <18.5 underweight, 18.5-24.9 "
    "normal, 25-29.9 overweight, 30-34.9 obese I, 35-39.9 obese II, "
    ">=40 obese III. The severe-underweight sub-band (<17.0) is this "
    "engine's own safety threshold, not a WHO category.",
)

PROTEIN_TARGETS = Reference(
    citation="Common sports-nutrition/clinical protein intake ranges: "
    "~1.2 g/kg maintenance, ~1.6 g/kg for weight loss (to preserve lean "
    "mass in a deficit), ~1.8 g/kg for muscle gain, with an elderly floor "
    "around 1.2 g/kg/day reflecting reduced anabolic sensitivity "
    "(cf. PROT-AGE study group recommendations), capped at 2.2 g/kg.",
    note="Ranges synthesized from commonly cited sports-nutrition and "
    "geriatric-nutrition guidance, not a single primary source.",
)

FAT_TARGETS = Reference(
    citation="Common minimum fat intake guidance: >= 0.8 g/kg/day or "
    "20-35% of total energy, to support hormone production and "
    "fat-soluble vitamin absorption.",
)

FIBER_DRI = Reference(
    citation="Institute of Medicine (US). Dietary Reference Intakes for "
    "Energy, Carbohydrate, Fiber, Fat, Fatty Acids, Cholesterol, Protein, "
    "and Amino Acids. 2005. (14 g fiber per 1000 kcal).",
    note="A 25 g/day floor is applied for low-calorie targets where the "
    "per-1000kcal formula would otherwise fall below what's considered "
    "a reasonable minimum.",
)

HYDRATION_GUIDANCE = Reference(
    citation="Common hydration guidance of ~35 mL/kg/day for adults, with "
    "an additional allowance for high activity levels.",
)

ATWATER_FACTORS = Reference(
    citation="Atwater WO. General principles governing composition and "
    "nutritive value of food. USDA, 1902 (values still in standard use: "
    "protein 4 kcal/g, carbohydrate 4 kcal/g, fat 9 kcal/g).",
    note="This engine deliberately omits fiber's ~2 kcal/g and treats "
    "fiber as a carbohydrate subset so 4P+4C+9F == kcal holds exactly "
    "everywhere (targets, food DB, validator).",
)

GUARDRAIL_AGE_RANGES = Reference(
    citation="Mifflin-St Jeor and this engine's macro targets are derived "
    "for healthy, non-pregnant adults; pediatric/adolescent energy needs "
    "require growth-adjusted equations (e.g. Schofield, DRI-EER) this "
    "engine does not implement, hence the hard age gates.",
)

CONDITION_SCREEN_REF = Reference(
    citation="Internal safety policy: keyword screen for conditions where "
    "automated calorie/macro targets are inappropriate without clinical "
    "supervision (pregnancy, lactation, diabetes, renal disease/dialysis, "
    "eating disorders, active cancer treatment, post-bariatric surgery, "
    "warfarin therapy).",
    note="This is a best-effort keyword fallback, not a guarantee — it can "
    "miss conditions not phrased with a listed keyword. It never replaces "
    "the server-injected disclaimer, which is unconditional.",
)

PLAN_TOLERANCES_RATIONALE = Reference(
    citation="Internal design decision, not an external nutrition "
    "reference: tolerances balance realism (integer-gram food plans "
    "rarely hit a calorie target exactly) against the clinical floors "
    "that must not be crossed (fat and protein have asymmetric bands).",
)

RETRIEVAL_THRESHOLD_RATIONALE = Reference(
    citation="Internal design decision: cosine-similarity threshold for "
    "text-embedding-3-small, tuned empirically against a labeled "
    "in-domain/out-of-domain query set (see scripts/tune_threshold.py). "
    "The value here is a conservative placeholder until that script has "
    "run against the real corpus; treat it as provisional.",
)


REFERENCES: dict[str, Reference] = {
    "IBW_HEIGHT_THRESHOLD_CM": DEVINE_IBW,
    "IBW_BASE_KG_MALE": DEVINE_IBW,
    "IBW_BASE_KG_FEMALE": DEVINE_IBW,
    "IBW_PER_INCH_OVER_KG": DEVINE_IBW,
    "CM_PER_INCH": Reference(citation="Unit conversion constant (exact)."),
    "ADJUSTED_BW_FACTOR": ADJUSTED_BW,
    "BMI_SEVERE_UNDERWEIGHT_MAX": WHO_BMI_CATEGORIES,
    "BMI_UNDERWEIGHT_MAX": WHO_BMI_CATEGORIES,
    "BMI_NORMAL_MAX": WHO_BMI_CATEGORIES,
    "BMI_OVERWEIGHT_MAX": WHO_BMI_CATEGORIES,
    "BMI_OBESE_I_MAX": WHO_BMI_CATEGORIES,
    "BMI_OBESE_II_MAX": WHO_BMI_CATEGORIES,
    "MSJ_WEIGHT_COEF": MIFFLIN,
    "MSJ_HEIGHT_COEF": MIFFLIN,
    "MSJ_AGE_COEF": MIFFLIN,
    "MSJ_SEX_CONST_MALE": MIFFLIN,
    "MSJ_SEX_CONST_FEMALE": MIFFLIN,
    "ACTIVITY_MULTIPLIERS": HARRIS_BENEDICT_ACTIVITY,
    "GOAL_TDEE_ADJUSTMENT": GOAL_ADJUSTMENT,
    "BMR_RELATIVE_FLOOR_FACTOR": CALORIE_FLOORS,
    "ABSOLUTE_CALORIE_FLOOR": CALORIE_FLOORS,
    "DEFICIT_RELAXATION_STEPS": GOAL_ADJUSTMENT,
    "TDEE_UNCERTAINTY_PCT": HARRIS_BENEDICT_ACTIVITY,
    "PROTEIN_G_PER_KG": PROTEIN_TARGETS,
    "PROTEIN_G_PER_KG_ELDERLY_MIN": PROTEIN_TARGETS,
    "PROTEIN_ELDERLY_AGE_THRESHOLD": PROTEIN_TARGETS,
    "PROTEIN_G_PER_KG_MAX": PROTEIN_TARGETS,
    "FAT_G_PER_KG_MIN": FAT_TARGETS,
    "FAT_KCAL_PCT_MIN": FAT_TARGETS,
    "FAT_KCAL_PCT_MAX": FAT_TARGETS,
    "KCAL_PER_G_PROTEIN": ATWATER_FACTORS,
    "KCAL_PER_G_CARB": ATWATER_FACTORS,
    "KCAL_PER_G_FAT": ATWATER_FACTORS,
    "FIBER_G_PER_1000KCAL": FIBER_DRI,
    "FIBER_G_MIN": FIBER_DRI,
    "HYDRATION_ML_PER_KG": HYDRATION_GUIDANCE,
    "HYDRATION_ML_MIN": HYDRATION_GUIDANCE,
    "HYDRATION_ML_MAX": HYDRATION_GUIDANCE,
    "HYDRATION_ML_VERY_ACTIVE_BONUS": HYDRATION_GUIDANCE,
    "AGE_CHILD_MAX": GUARDRAIL_AGE_RANGES,
    "AGE_MINOR_MAX": GUARDRAIL_AGE_RANGES,
    "AGE_ELDERLY_MIN": GUARDRAIL_AGE_RANGES,
    "AGE_IMPLAUSIBLE_MIN": GUARDRAIL_AGE_RANGES,
    "HEIGHT_CM_MIN": GUARDRAIL_AGE_RANGES,
    "HEIGHT_CM_MAX": GUARDRAIL_AGE_RANGES,
    "WEIGHT_KG_MIN": GUARDRAIL_AGE_RANGES,
    "WEIGHT_KG_MAX": GUARDRAIL_AGE_RANGES,
    "BMI_UNDERWEIGHT_DEFICIT_BLOCK_MAX": WHO_BMI_CATEGORIES,
    "BMI_CLASS_III_MAX_DEFICIT_PCT": WHO_BMI_CATEGORIES,
    "CONDITION_SCREEN_KEYWORDS": CONDITION_SCREEN_REF,
    "RETRIEVAL_MIN_SCORE": RETRIEVAL_THRESHOLD_RATIONALE,
    "RETRIEVAL_TOP_K": RETRIEVAL_THRESHOLD_RATIONALE,
    "RETRIEVAL_KEEP_ABOVE_THRESHOLD": RETRIEVAL_THRESHOLD_RATIONALE,
    "KCAL_TOLERANCE_PCT": PLAN_TOLERANCES_RATIONALE,
    "KCAL_TOLERANCE_MIN_ABS": PLAN_TOLERANCES_RATIONALE,
    "PROTEIN_TOLERANCE_UNDER_PCT": PLAN_TOLERANCES_RATIONALE,
    "PROTEIN_TOLERANCE_OVER_PCT": PLAN_TOLERANCES_RATIONALE,
    "FAT_TOLERANCE_PCT": PLAN_TOLERANCES_RATIONALE,
    "CARB_TOLERANCE_PCT": PLAN_TOLERANCES_RATIONALE,
    "FIBER_TOLERANCE_MIN_FRACTION": PLAN_TOLERANCES_RATIONALE,
    "PLAN_ITEM_GRAMS_MIN": PLAN_TOLERANCES_RATIONALE,
    "PLAN_ITEM_GRAMS_MAX": PLAN_TOLERANCES_RATIONALE,
    "PLAN_MEAL_GRAMS_MAX": PLAN_TOLERANCES_RATIONALE,
    "FIT_SCALE_MIN": PLAN_TOLERANCES_RATIONALE,
    "FIT_SCALE_MAX": PLAN_TOLERANCES_RATIONALE,
    "FIT_MAX_GREEDY_ITERATIONS": PLAN_TOLERANCES_RATIONALE,
    "FOOD_DB_ATWATER_TOLERANCE_PCT": ATWATER_FACTORS,
}
