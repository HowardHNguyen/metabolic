// The app's in-browser copy of the production model (identical to the API's; see riskModel.js).
// Used for the What-If sliders (instant, no network) and as an exact offline fallback.
import spec from "./model.json";
import { createRiskModel } from "./riskModel.js";

export const MODEL = createRiskModel(spec);
export const MODEL_SPEC = spec;
