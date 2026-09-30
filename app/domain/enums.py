"""Enums shared across the domain engine, the API schema, and the frontend.

Keeping these as plain str-Enums (not free text) is what makes the engine
possible in the first place: `activity_level` and `goal` used to be free
Italian text on the frontend ("abbastanza attivo"), which cannot be mapped to
a PAL multiplier. The frontend must send one of these exact values.
"""

from __future__ import annotations

from enum import Enum


class Sex(str, Enum):
    MALE = "male"
    FEMALE = "female"


class ActivityLevel(str, Enum):
    SEDENTARY = "sedentary"
    LIGHT = "light"
    MODERATE = "moderate"
    ACTIVE = "active"
    VERY_ACTIVE = "very_active"


class Goal(str, Enum):
    LOSE_WEIGHT = "lose_weight"
    MAINTAIN = "maintain"
    GAIN_MUSCLE = "gain_muscle"


class BmiCategory(str, Enum):
    SEVERE_UNDERWEIGHT = "severe_underweight"
    UNDERWEIGHT = "underweight"
    NORMAL = "normal"
    OVERWEIGHT = "overweight"
    OBESE_I = "obese_class_1"
    OBESE_II = "obese_class_2"
    OBESE_III = "obese_class_3"


class Severity(str, Enum):
    REFUSE = "refuse"
    WARN = "warn"


class ViolationCode(str, Enum):
    AGE_CHILD = "AGE_CHILD"
    AGE_MINOR = "AGE_MINOR"
    AGE_ELDERLY = "AGE_ELDERLY"
    AGE_IMPLAUSIBLE = "AGE_IMPLAUSIBLE"
    HEIGHT_RANGE = "HEIGHT_RANGE"
    WEIGHT_RANGE = "WEIGHT_RANGE"
    BMI_SEVERE_UNDERWEIGHT = "BMI_SEVERE_UNDERWEIGHT"
    BMI_UNDERWEIGHT = "BMI_UNDERWEIGHT"
    BMI_CLASS_III = "BMI_CLASS_III"
    GOAL_CONFLICT_DEFICIT = "GOAL_CONFLICT_DEFICIT"
    CONDITION_SCREEN = "CONDITION_SCREEN"
    DEFICIT_RELAXED_FOR_FLOORS = "DEFICIT_RELAXED_FOR_FLOORS"
