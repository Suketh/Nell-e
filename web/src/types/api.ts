export type ProgressState = {
  xp: number;
  level: number;
  stage: string;
  next_gallery_unlock?: string;
  next_tool_unlock?: string | { level: number; label: string };
};

export type GalleryItem = {
  path?: string;
  title?: string;
  caption?: string;
  reason_text?: string;
  level_min?: number;
  content_type?: string;
  tone?: string;
  visibility?: string;
  tags?: string[];
};

export type ProfileSummary = {
  user_id: string;
  session_id?: string;
  progress: ProgressState;
  gallery_unlock_count: number;
  latest_unlock?: GalleryItem | null;
};

export type ReplyResponse = {
  user_id: string;
  session_id: string;
  reply: string;
  mood: string;
  context?: string;
  mode: string;
  tool_events: string[];
  agent_trace: string[];
  gallery_image_path: string;
  gallery_image_caption: string;
  new_unlock?: GalleryItem | Record<string, never>;
};

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  text: string;
  mood?: string;
};

export type WebProfile = {
  userId: string;
  displayName: string;
  badgeColor: string;
};
