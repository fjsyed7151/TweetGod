import { createClient } from '@/lib/supabase/server';
import type { DailyTrendDataPoint } from '@/lib/types';
import { calculateEngagementRate } from '@/lib/utils';

export async function getDailyTrends(days: number = 30): Promise<DailyTrendDataPoint[]> {
  const supabase = await createClient();
  const startDate = new Date();
  startDate.setDate(startDate.getDate() - days);
  startDate.setHours(0, 0, 0, 0);

  const { data, error } = await supabase
    .from('replied_tweets')
    .select('posted_at, engagement_likes, engagement_impressions')
    .gte('posted_at', startDate.toISOString())
    .order('posted_at', { ascending: true });

  if (error) {
    console.error('Error fetching trends:', error);
    return [];
  }

  // Group by date
  const grouped = new Map<string, { replies: number; likes: number; impressions: number }>();

  for (const row of data ?? []) {
    const date = new Date(row.posted_at).toISOString().split('T')[0];
    const existing = grouped.get(date) ?? { replies: 0, likes: 0, impressions: 0 };
    existing.replies += 1;
    existing.likes += row.engagement_likes ?? 0;
    existing.impressions += row.engagement_impressions ?? 0;
    grouped.set(date, existing);
  }

  // Fill in missing dates
  const result: DailyTrendDataPoint[] = [];
  const current = new Date(startDate);
  const now = new Date();

  while (current <= now) {
    const dateStr = current.toISOString().split('T')[0];
    const dayData = grouped.get(dateStr) ?? { replies: 0, likes: 0, impressions: 0 };
    result.push({
      date: dateStr,
      replies: dayData.replies,
      likes: dayData.likes,
      impressions: dayData.impressions,
      engagementRate: calculateEngagementRate(dayData.likes, dayData.impressions),
    });
    current.setDate(current.getDate() + 1);
  }

  return result;
}
