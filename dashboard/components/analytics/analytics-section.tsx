import { getStyleStats } from '@/lib/data/stats';
import { calculateEngagementRate } from '@/lib/utils';
import type { StylePerformance } from '@/lib/types';
import { StyleCard } from './style-card';
import { StyleComparisonChart } from './style-comparison-chart';
import { TrendsSection } from './trends-section';
import { Separator } from '@/components/ui/separator';

export async function AnalyticsSection() {
  const stats = await getStyleStats();

  const styles: StylePerformance[] = stats.map((s) => ({
    ...s,
    successRate: s.attempts > 0 ? (s.successes / s.attempts) * 100 : 0,
    avgLikesPerReply: s.successes > 0 ? s.total_likes / s.successes : 0,
    engagementRate: calculateEngagementRate(s.total_likes, s.total_impressions),
  }));

  return (
    <div className="space-y-6">
      <div className="space-y-4">
        <h2 className="text-lg font-semibold">Style Performance</h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
          {styles.length > 0 ? (
            styles.map((s) => <StyleCard key={s.style} style={s} />)
          ) : (
            <div className="col-span-full py-8 text-center text-muted-foreground">No style data yet.</div>
          )}
        </div>
      </div>

      <StyleComparisonChart styles={styles} />

      <Separator />

      <TrendsSection />
    </div>
  );
}
