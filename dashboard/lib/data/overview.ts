import { createClient } from '@/lib/supabase/server';
import type { OverviewStats } from '@/lib/types';
import { calculateEngagementRate } from '@/lib/utils';

export async function getOverviewStats(): Promise<OverviewStats> {
  const supabase = await createClient();

  // Get today's replies count
  const today = new Date();
  today.setHours(0, 0, 0, 0);

  const [todayResult, totalResult, keywordResult, styleResult] = await Promise.all([
    supabase
      .from('replied_tweets')
      .select('tweet_id', { count: 'exact', head: true })
      .gte('posted_at', today.toISOString()),
    supabase
      .from('replied_tweets')
      .select('engagement_likes, engagement_impressions', { count: 'exact' }),
    supabase
      .from('keyword_stats')
      .select('*')
      .order('successes', { ascending: false })
      .limit(1),
    supabase
      .from('style_stats')
      .select('*')
      .order('successes', { ascending: false })
      .limit(1),
  ]);

  const totalReplies = totalResult.count ?? 0;
  const repliesToday = todayResult.count ?? 0;

  // Calculate totals from replied_tweets
  const replies = totalResult.data ?? [];
  const totalLikes = replies.reduce((sum, r) => sum + (r.engagement_likes ?? 0), 0);
  const totalImpressions = replies.reduce((sum, r) => sum + (r.engagement_impressions ?? 0), 0);
  const avgEngagementRate = calculateEngagementRate(totalLikes, totalImpressions);

  const bestKeywordData = keywordResult.data?.[0];
  const bestStyleData = styleResult.data?.[0];

  return {
    repliesToday,
    totalReplies,
    avgEngagementRate,
    bestKeyword: bestKeywordData
      ? {
          keyword: bestKeywordData.keyword,
          successRate: bestKeywordData.attempts > 0
            ? (bestKeywordData.successes / bestKeywordData.attempts) * 100
            : 0,
        }
      : null,
    bestStyle: bestStyleData
      ? {
          style: bestStyleData.style,
          successRate: bestStyleData.attempts > 0
            ? (bestStyleData.successes / bestStyleData.attempts) * 100
            : 0,
        }
      : null,
    totalLikes,
    totalImpressions,
  };
}
