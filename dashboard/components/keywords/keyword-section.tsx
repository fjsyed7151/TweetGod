import { getKeywordStats } from '@/lib/data/stats';
import { KeywordPerformanceTable } from './keyword-performance-table';
import { calculateEngagementRate } from '@/lib/utils';
import type { KeywordPerformance } from '@/lib/types';

export async function KeywordSection() {
  const stats = await getKeywordStats();

  const keywords: KeywordPerformance[] = stats.map((kw) => ({
    ...kw,
    successRate: kw.attempts > 0 ? (kw.successes / kw.attempts) * 100 : 0,
    avgLikesPerReply: kw.successes > 0 ? kw.total_likes / kw.successes : 0,
    engagementRate: calculateEngagementRate(kw.total_likes, kw.total_impressions),
  }));

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold">Keyword Performance</h2>
      <KeywordPerformanceTable keywords={keywords} />
    </div>
  );
}
