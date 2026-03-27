import { getOverviewStats } from '@/lib/data/overview';
import { StatCard } from './stat-card';
import { formatNumber } from '@/lib/utils';
import { MessageSquare, TrendingUp, Hash, Palette } from 'lucide-react';

export async function OverviewStats() {
  const stats = await getOverviewStats();

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <StatCard
        title="Replies Today"
        value={stats.repliesToday}
        subtitle={`${formatNumber(stats.totalReplies)} total`}
        icon={MessageSquare}
        iconColor="text-blue-500"
      />
      <StatCard
        title="Engagement Rate"
        value={`${stats.avgEngagementRate.toFixed(2)}%`}
        subtitle={`${formatNumber(stats.totalLikes)} likes / ${formatNumber(stats.totalImpressions)} impressions`}
        icon={TrendingUp}
        iconColor="text-green-500"
      />
      <StatCard
        title="Best Keyword"
        value={stats.bestKeyword?.keyword ?? 'N/A'}
        subtitle={stats.bestKeyword ? `${stats.bestKeyword.successRate.toFixed(0)}% success rate` : 'No data yet'}
        icon={Hash}
        iconColor="text-purple-500"
      />
      <StatCard
        title="Best Style"
        value={stats.bestStyle?.style ?? 'N/A'}
        subtitle={stats.bestStyle ? `${stats.bestStyle.successRate.toFixed(0)}% success rate` : 'No data yet'}
        icon={Palette}
        iconColor="text-orange-500"
      />
    </div>
  );
}
