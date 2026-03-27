// Reply styles used in the bot
export type ReplyStyle = 'witty' | 'insightful' | 'contrarian' | 'supportive' | 'quick_reaction' | 'custom';

// Source types for how tweets were found
export type SourceType = 'keyword' | 'priority' | 'trending' | 'community';

// Review outcomes
export type ReviewOutcome = 'approved' | 'edited' | 'rejected' | 'auto_approved';

// Database row types
export interface RepliedTweet {
  tweet_id: string;
  reply_tweet_id: string | null;
  author_username: string;
  reply_text: string;
  tweet_url: string | null;
  keyword: string | null;
  score: number;
  posted_at: string;
  engagement_likes: number | null;
  engagement_impressions: number | null;
  engagement_checked: string | null;
  reply_style: ReplyStyle | null;
  source_type: SourceType | null;
}

export interface KeywordStats {
  keyword: string;
  attempts: number;
  successes: number;
  total_likes: number;
  total_impressions: number;
  last_used: string | null;
  last_success: string | null;
}

export interface StyleStats {
  style: string;
  attempts: number;
  successes: number;
  total_likes: number;
  total_impressions: number;
  last_used: string | null;
  last_success: string | null;
}

export interface ReplyReview {
  id: string;
  tweet_id: string;
  author_username: string | null;
  tweet_text: string | null;
  tweet_url: string | null;
  ai_reply_text: string;
  final_reply_text: string;
  outcome: ReviewOutcome;
  reply_style: ReplyStyle | null;
  source_type: SourceType | null;
  score: number | null;
  keyword: string | null;
  reviewed_at: string | null;
  response_time_seconds: number | null;
}

// Derived types for the dashboard
export interface OverviewStats {
  repliesToday: number;
  totalReplies: number;
  avgEngagementRate: number;
  bestKeyword: { keyword: string; successRate: number } | null;
  bestStyle: { style: string; successRate: number } | null;
  totalLikes: number;
  totalImpressions: number;
}

export interface KeywordPerformance extends KeywordStats {
  successRate: number;
  avgLikesPerReply: number;
  engagementRate: number;
}

export interface StylePerformance extends StyleStats {
  successRate: number;
  avgLikesPerReply: number;
  engagementRate: number;
}

export interface DailyTrendDataPoint {
  date: string;
  replies: number;
  likes: number;
  impressions: number;
  engagementRate: number;
}
