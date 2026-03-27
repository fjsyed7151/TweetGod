import { getDailyTrends } from '@/lib/data/trends';
import { DailyTrendsChart } from './daily-trends-chart';

export async function TrendsSection() {
  const trends = await getDailyTrends(30);

  return (
    <div className="space-y-4">
      <h3 className="text-base font-semibold">30-Day Trends</h3>
      <div className="grid gap-4 lg:grid-cols-1">
        <DailyTrendsChart
          data={trends}
          title="Replies per Day"
          dataKey="replies"
          color="hsl(217, 91%, 60%)"
        />
        <DailyTrendsChart
          data={trends}
          title="Likes per Day"
          dataKey="likes"
          color="hsl(142, 76%, 36%)"
        />
        <DailyTrendsChart
          data={trends}
          title="Engagement Rate Over Time"
          dataKey="engagementRate"
          color="hsl(25, 95%, 53%)"
          formatAsPercent
        />
      </div>
    </div>
  );
}
