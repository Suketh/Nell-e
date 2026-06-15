export type ProgressState = {
  xp: number;
  level: number;
  stage: string;
  last_reason?: string;
  xp_into_level?: number;
  xp_for_next_level?: number;
  xp_to_next_level?: number;
  unlocked_tools?: string[];
  next_gallery_unlock?: { level: number; title: string; tone?: string; visibility?: string } | string;
  next_tool_unlock?: string | { level: number; label: string };
};

export type NextFeatureUnlock = {
  id: string;
  label: string;
  description: string;
  category: string;
  level: number;
  implemented: boolean;
};

export type NelliePreference = {
  id: string;
  label: string;
  value: string;
  confidence: number;
  count: number;
};

export type VoiceProfile = {
  id: string;
  label: string;
  description?: string;
  sample?: string;
};

export type PersonaProfile = {
  id: string;
  name: string;
  label?: string;
  description?: string;
  voice_profile_id?: string;
};

export type ToolEvent = {
  tool?: string;
  status?: string;
  [key: string]: unknown;
};

export type AgentTraceEvent = {
  step?: string;
  status?: string;
  [key: string]: unknown;
};

export type FeatureAccessItem = {
  id: string;
  label: string;
  description: string;
  category: string;
  min_level: number;
  implemented: boolean;
  default_enabled?: boolean;
  unlocked: boolean;
  enabled: boolean;
};

export type FeatureAccessState = {
  items: FeatureAccessItem[];
  enabled_ids: string[];
  enabled_count: number;
  available_count: number;
};

export type GalleryItem = {
  filename?: string;
  image_path?: string;
  path?: string;
  title?: string;
  caption?: string;
  reason_text?: string;
  level_min?: number;
  content_type?: string;
  tone?: string;
  visibility?: string;
  tags?: string[];
  unlocked?: boolean;
};

export type ProfileSummary = {
  user_id: string;
  session_id?: string;
  progress: ProgressState;
  feature_access?: FeatureAccessState;
  gallery_unlock_count: number;
  latest_unlock?: GalleryItem | null;
  enabled_feature_labels?: string[];
  available_feature_labels?: string[];
  next_feature_unlock?: NextFeatureUnlock | null;
  stage_copy?: string;
  practical_focus?: string;
  suggested_prompts?: string[];
  nellie_preferences?: NelliePreference[];
  voice_profiles?: VoiceProfile[];
  selected_voice_profile?: VoiceProfile | null;
  persona_id?: string;
  persona_profiles?: PersonaProfile[];
  selected_persona?: PersonaProfile | null;
};

export type ReplyResponse = {
  user_id: string;
  session_id: string;
  reply: string;
  spoken_reply?: string;
  tts_audio_base64?: string;
  tts_audio_content_type?: string;
  tts_sample_rate?: number;
  tts_meta?: {
    engine?: string;
    cache_hit?: boolean;
    tts_ms?: number;
    profile_id?: string;
    text_chars?: number;
    language?: string;
  };
  tts_error?: {
    code?: string;
    message?: string;
    request_id?: string;
  };
  mood: string;
  context?: string;
  mode: string;
  tool_events: ToolEvent[];
  agent_trace: AgentTraceEvent[];
  gallery_image_path: string;
  gallery_image_caption: string;
  new_unlock?: GalleryItem | Record<string, never>;
  progress?: ProgressState;
  feature_access?: FeatureAccessState;
  gallery_unlock_count?: number;
  latest_unlock?: GalleryItem | null;
  enabled_feature_labels?: string[];
  available_feature_labels?: string[];
  next_feature_unlock?: NextFeatureUnlock | null;
  stage_copy?: string;
  practical_focus?: string;
  suggested_prompts?: string[];
  nellie_preferences?: NelliePreference[];
  voice_profiles?: VoiceProfile[];
  selected_voice_profile?: VoiceProfile | null;
  persona_id?: string;
  persona_profiles?: PersonaProfile[];
  selected_persona?: PersonaProfile | null;
};

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  text: string;
  spokenText?: string;
  mood?: string;
};

export type MobileProfile = {
  userId: string;
  displayName: string;
  badgeColor: string;
  isAdmin?: boolean;
};
