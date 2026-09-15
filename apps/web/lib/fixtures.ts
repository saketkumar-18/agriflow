// Fixture data for DEMO mode — used ONLY when the API server is unreachable,
// and always rendered with a visible "DEMO DATA" banner (never silent).

import type {
  AdminStats,
  AppNotification,
  Crop,
  FarmAnalytics,
  FarmSummary,
  FieldDetail,
  HistoryResponse,
  IrrigationEvent,
  Paginated,
  Recommendation,
  SoilType,
} from "@/lib/types";

function hoursAgoIso(h: number): string {
  return new Date(Date.now() - h * 3_600_000).toISOString();
}
function dayStr(offsetDays: number): string {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  return d.toISOString().slice(0, 10);
}

export const demoRecommendation: Recommendation = {
  id: 9001,
  field_id: 1,
  computed_at: hoursAgoIso(2),
  expires_at: hoursAgoIso(-10),
  irrigation_needed: true,
  urgency: "HIGH",
  recommended_time: { key: "time.tomorrow_morning", params: {} },
  estimated_water_requirement: { value: 18, unit: "mm" },
  estimated_liters: 180000,
  confidence: {
    score: 0.82,
    level: "HIGH",
    factors: [
      { key: "conf.has_recent_moisture", ok: true },
      { key: "conf.weather_available", ok: true },
      { key: "conf.missing_moisture", ok: false },
    ],
  },
  reasons: [
    { key: "reasons.soil_below_target", params: { value: 31, target: 45 } },
    { key: "reasons.no_rain_expected", params: { days: 4 } },
    { key: "reasons.critical_stage", params: { stage: "Vegetative" } },
  ],
  warnings: [{ key: "warnings.stale_moisture", params: { age_hours: 5 } }],
  inputs_digest: {
    moisture: { value: 31, source: "manual", age_hours: 5 },
    rain_next_24h_mm: 0,
    et0_mm: 4.8,
    crop: "Wheat",
    stage: "VEGETATIVE",
    soil: "Loamy",
  },
  engine_version: "rules-1.0",
  override: null,
  disclaimer_key: "rec.disclaimer",
  demo: true,
};

const demoRecommendationOk: Recommendation = {
  ...demoRecommendation,
  id: 9002,
  field_id: 2,
  irrigation_needed: false,
  urgency: "LOW",
  recommended_time: null,
  estimated_water_requirement: null,
  estimated_liters: null,
  reasons: [
    { key: "reasons.soil_above_target", params: { value: 52, target: 45 } },
    { key: "reasons.rain_expected", params: { mm: 12, hours: 36 } },
  ],
  warnings: [],
};

export const demoFarmSummary: FarmSummary = {
  farm: {
    id: 1,
    name: "Demo Farm — Assam",
    location_text: "Near Guwahati, Assam",
    latitude: 26.14,
    longitude: 91.72,
    total_area: 2.5,
    area_unit: "ha",
    field_count: 2,
    created_at: hoursAgoIso(24 * 90),
    updated_at: hoursAgoIso(24),
    demo: true,
  },
  fields: [
    {
      id: 1,
      name: "Field A",
      crop_name: "Wheat",
      growth_stage: "VEGETATIVE",
      soil_moisture: { value: 31, source: "manual", measured_at: hoursAgoIso(5), age_hours: 5 },
      recommendation: demoRecommendation,
      status: "needs_irrigation",
    },
    {
      id: 2,
      name: "Field B",
      crop_name: "Paddy",
      growth_stage: "FLOWERING",
      soil_moisture: { value: 52, source: "sensor", measured_at: hoursAgoIso(1), age_hours: 1 },
      recommendation: demoRecommendationOk,
      status: "ok",
    },
  ],
  weather_snapshot: {
    available: true,
    provider: "open-meteo (demo)",
    fetched_at: hoursAgoIso(1),
    latitude: 26.14,
    longitude: 91.72,
    current: {
      temp_c: 28.1,
      humidity_pct: 61,
      wind_kmh: 11,
      rain_prob_pct: 20,
      condition_code: 2,
      observed_at: hoursAgoIso(1),
    },
    forecast: [
      { day: dayStr(0), min_c: 22, max_c: 31, rain_prob_pct: 20, rain_mm: 0, condition_code: 2 },
      { day: dayStr(1), min_c: 22, max_c: 30, rain_prob_pct: 15, rain_mm: 0, condition_code: 1 },
      { day: dayStr(2), min_c: 23, max_c: 32, rain_prob_pct: 35, rain_mm: 2, condition_code: 3 },
      { day: dayStr(3), min_c: 23, max_c: 29, rain_prob_pct: 80, rain_mm: 14, condition_code: 63 },
      { day: dayStr(4), min_c: 22, max_c: 28, rain_prob_pct: 60, rain_mm: 6, condition_code: 61 },
    ],
    recent_rainfall_mm: { last_24h: 0, last_72h: 4.5, last_7d: 12 },
    alert: null,
  },
  generated_at: hoursAgoIso(2),
};

export const demoFieldDetail: FieldDetail = {
  field: {
    id: 1,
    farm_id: 1,
    name: "Field A",
    area: 1.0,
    area_unit: "ha",
    soil_type: {
      id: 1,
      name: "Loamy",
      field_capacity_pct: 45,
      wilting_point_pct: 18,
      bulk_density: 1.4,
      water_holding_capacity_mm_per_m: 150,
      is_estimate: true,
      label_key: "soil.loamy",
    },
    crop: { id: 1, name: "Wheat", stages: [{ code: "VEGETATIVE", kc: 1.1, critical: true, label_key: "crop.stage.VEGETATIVE" }] },
    growth_stage_code: "VEGETATIVE",
    irrigation_method: "furrow",
    water_source: "Tube well",
    boundary_geojson: null,
    sensor_present: false,
    created_at: hoursAgoIso(24 * 60),
    updated_at: hoursAgoIso(24),
    demo: true,
  },
  latest_reading: { id: 1, field_id: 1, value_pct: 31, source: "manual", taken_at: hoursAgoIso(5), demo: true },
  recommendation: demoRecommendation,
  weather: demoFarmSummary.weather_snapshot,
};

export const demoHistory: HistoryResponse = {
  field_id: 1,
  from: dayStr(-29),
  to: dayStr(0),
  soil_moisture: Array.from({ length: 30 }, (_, i) => ({
    t: dayStr(i - 29) + "T09:00:00Z",
    value: Math.round((38 + 12 * Math.sin(i / 4.5) - i * 0.25) * 10) / 10,
    source: i % 5 === 0 ? "manual" : "sensor",
  })),
  rainfall_mm: Array.from({ length: 30 }, (_, i) => ({
    day: dayStr(i - 29),
    value: i % 9 === 3 ? [2, 4, 0.5, 8][i % 4] : 0,
    kind: i >= 25 ? ("forecast" as const) : ("observed" as const),
  })),
  temperature_c: Array.from({ length: 30 }, (_, i) => ({
    day: dayStr(i - 29),
    min: 21 + Math.round(3 * Math.sin(i / 6)),
    max: 30 + Math.round(4 * Math.sin(i / 5)),
  })),
  irrigation_mm: Array.from({ length: 30 }, (_, i) => ({
    day: dayStr(i - 29),
    value: i % 7 === 1 ? 16 + (i % 3) * 2 : 0,
  })),
  et0_mm: Array.from({ length: 30 }, (_, i) => ({
    day: dayStr(i - 29),
    value: Math.round((4 + Math.sin(i / 7) * 1.4) * 10) / 10,
    kind: "estimated",
  })),
  etc_mm: Array.from({ length: 30 }, (_, i) => ({
    day: dayStr(i - 29),
    value: Math.round((4 + Math.sin(i / 7) * 1.4) * 1.05 * 10) / 10,
    kind: "estimated",
  })),
};

export const demoIrrigationEvents: Paginated<IrrigationEvent> = {
  items: [
    { id: 1, field_id: 1, recommendation_id: 9001, irrigated_at: hoursAgoIso(30), duration_minutes: 45, amount_mm: 18, liters: 180000, note: "Evening irrigation", source: "manual", demo: true },
    { id: 2, field_id: 1, recommendation_id: null, irrigated_at: hoursAgoIso(30 * 3), duration_minutes: 60, amount_mm: 22, liters: 220000, note: null, source: "manual", demo: true },
    { id: 3, field_id: 2, recommendation_id: null, irrigated_at: hoursAgoIso(30 * 6), duration_minutes: 30, amount_mm: 12, liters: 120000, note: "Pre-sowing", source: "manual", demo: true },
  ],
  page: 1,
  page_size: 20,
  total: 3,
};

export const demoNotifications: Paginated<AppNotification> = {
  items: [
    { id: 1, type: "irrigation_needed", severity: "high", title_key: "notif.type.irrigation_needed", params: { field: "Field A" }, created_at: hoursAgoIso(2), read_at: null },
    { id: 2, type: "rain_incoming", severity: "medium", title_key: "notif.type.rain_incoming", params: { day: dayStr(3) }, created_at: hoursAgoIso(10), read_at: null },
    { id: 3, type: "extreme_heat", severity: "high", title_key: "notif.type.extreme_heat", params: {}, created_at: hoursAgoIso(50), read_at: hoursAgoIso(40) },
  ],
  page: 1,
  page_size: 20,
  total: 3,
};

export const demoAnalytics: FarmAnalytics = {
  month: dayStr(0).slice(0, 7),
  total_irrigation_liters: 420000,
  recommended_liters: 385000,
  potential_difference_liters: 35000,
  wording_key: "analytics.potential_reduction_note",
  events_count: 6,
  fields: [],
  weekly: [
    { week: dayStr(-24), irrigated_liters: 110000, recommended_liters: 95000 },
    { week: dayStr(-17), irrigated_liters: 98000, recommended_liters: 102000 },
    { week: dayStr(-10), irrigated_liters: 122000, recommended_liters: 100000 },
    { week: dayStr(-3), irrigated_liters: 90000, recommended_liters: 88000 },
  ],
};

export const demoCrops: Crop[] = [
  {
    id: 1,
    name: "Wheat",
    scientific_name: "Triticum aestivum",
    root_depth_mm: 600,
    maturity_days: 120,
    stages: [
      { code: "GERMINATION", kc: 0.4, critical: false, label_key: "crop.stage.GERMINATION" },
      { code: "VEGETATIVE", kc: 1.1, critical: true, label_key: "crop.stage.VEGETATIVE" },
      { code: "FLOWERING", kc: 1.2, critical: true, label_key: "crop.stage.FLOWERING" },
      { code: "MATURITY", kc: 0.5, critical: false, label_key: "crop.stage.MATURITY" },
    ],
    advisory_text_key: "advisory.wheat",
    demo: true,
  },
  {
    id: 2,
    name: "Paddy",
    scientific_name: "Oryza sativa",
    root_depth_mm: 500,
    maturity_days: 150,
    stages: [
      { code: "CULTIVATION", kc: 1.05, critical: false, label_key: "crop.stage.CULTIVATION" },
      { code: "FLOWERING", kc: 1.15, critical: true, label_key: "crop.stage.FLOWERING" },
      { code: "MATURITY", kc: 0.6, critical: false, label_key: "crop.stage.MATURITY" },
    ],
    advisory_text_key: "advisory.paddy",
    demo: true,
  },
];

export const demoSoilTypes: SoilType[] = [
  { id: 1, name: "Loamy", field_capacity_pct: 45, wilting_point_pct: 18, bulk_density: 1.4, water_holding_capacity_mm_per_m: 150, is_estimate: true, label_key: "soil.loamy" },
  { id: 2, name: "Clay", field_capacity_pct: 50, wilting_point_pct: 24, bulk_density: 1.3, water_holding_capacity_mm_per_m: 130, is_estimate: true, label_key: "soil.clay" },
  { id: 3, name: "Sandy", field_capacity_pct: 28, wilting_point_pct: 10, bulk_density: 1.6, water_holding_capacity_mm_per_m: 80, is_estimate: true, label_key: "soil.sandy" },
];

export const demoAdminStats: AdminStats = {
  total_users: 128,
  total_farms: 96,
  active_farms: 81,
  total_fields: 214,
  recommendations_today: 187,
  irrigation_events_30d: 640,
  sensor_uptime_pct: 97.4,
  weather_provider_health: "ok",
};
