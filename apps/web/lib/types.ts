// TypeScript view of the canonical model, matching the JSON the importer
// writes into a bundle (importer/src/qbank_importer/model/). Kept in sync via
// `qbank-import schema`, which exports JSON Schemas for these shapes.

export type ContentBlock =
  | { kind: "text"; text: string }
  | { kind: "verbatim"; text: string; language_hint?: string | null }
  | { kind: "image"; asset_id: string; caption?: string | null }
  | { kind: "table"; rows: string[][] };

export interface Item {
  id: string;
  label?: string | null;
  content: ContentBlock[];
}

export interface ChoiceInteraction {
  kind: "choice";
  options: Item[];
  correct_option_ids: string[];
}

export interface OrderingInteraction {
  kind: "ordering";
  items: Item[];
  correct_order: string[];
}

export interface MatchPair {
  left_id: string;
  right_id: string;
}

export interface MatchingInteraction {
  kind: "matching";
  left: Item[];
  right: Item[];
  pairs: MatchPair[];
}

export interface Placement {
  token_id: string;
  target_id: string;
}

export interface DragAndDropInteraction {
  kind: "drag_and_drop";
  tokens: Item[];
  targets: Item[];
  placements: Placement[];
}

export interface Blank {
  id: string;
  accepted: string[];
}

export interface FillInBlankInteraction {
  kind: "fill_in_blank";
  blanks: Blank[];
}

export type Interaction =
  | ChoiceInteraction
  | OrderingInteraction
  | MatchingInteraction
  | DragAndDropInteraction
  | FillInBlankInteraction;

export type QuestionType =
  | "single_choice"
  | "multiple_choice"
  | "true_false"
  | "drag_and_drop"
  | "matching"
  | "ordering"
  | "fill_in_blank"
  | "scenario"
  | "case_study";

export interface SourceRef {
  ordinal: number;
  label?: string | null;
  pages: number[];
}

export interface Question {
  id: string;
  source: SourceRef;
  type: QuestionType;
  group_id?: string | null;
  stem: ContentBlock[];
  interaction: Interaction;
  explanation: ContentBlock[];
}

export interface QuestionGroup {
  id: string;
  kind: "scenario" | "case_study";
  title?: string | null;
  context: ContentBlock[];
  question_ids: string[];
}

export interface BundleManifest {
  bundle_format_version: string;
  importer_version: string;
  created_at: string;
  source: {
    format: string;
    filename: string;
    sha256: string;
    size_bytes: number;
    page_count: number | null;
  };
  question_count: number;
  group_count: number;
  asset_count: number;
}

export interface LoadedBundle {
  manifest: BundleManifest;
  questions: Question[];
  groups: QuestionGroup[];
}
