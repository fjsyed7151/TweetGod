import { Card, CardContent } from '@/components/ui/card';
import { formatNumber } from '@/lib/utils';
import type { StylePerformance } from '@/lib/types';

const styleColors: Record<string, { bg: string; text: string; border: string }> = {
  sigma: { bg: 'bg-purple-500/10', text: 'text-purple-400', border: 'border-purple-500/30' },
  edgy_humor: { bg: 'bg-red-500/10', text: 'text-red-400', border: 'border-red-500/30' },
  motivational: { bg: 'bg-green-500/10', text: 'text-green-400', border: 'border-green-500/30' },
  hot_take: { bg: 'bg-orange-500/10', text: 'text-orange-400', border: 'border-orange-500/30' },
  absurdist: { bg: 'bg-cyan-500/10', text: 'text-cyan-400', border: 'border-cyan-500/30' },
};

interface StyleCardProps {
  style: StylePerformance;
}

export function StyleCard({ style }: StyleCardProps) {
  const colors = styleColors[style.style] ?? { bg: 'bg-muted', text: 'text-foreground', border: 'border-border' };

  return (
    <Card className={`${colors.border} border`}>
      <CardContent className="p-4">
        <div className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${colors.bg} ${colors.text} mb-3`}>
          {style.style.replace('_', ' ')}
        </div>
        <div className="grid grid-cols-2 gap-3 text-sm">
          <div>
            <p className="text-muted-foreground">Attempts</p>
            <p className="font-semibold">{style.attempts}</p>
          </div>
          <div>
            <p className="text-muted-foreground">Success Rate</p>
            <p className="font-semibold">{style.successRate.toFixed(0)}%</p>
          </div>
          <div>
            <p className="text-muted-foreground">Total Likes</p>
            <p className="font-semibold">{formatNumber(style.total_likes)}</p>
          </div>
          <div>
            <p className="text-muted-foreground">Engagement</p>
            <p className="font-semibold">{style.engagementRate.toFixed(2)}%</p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
