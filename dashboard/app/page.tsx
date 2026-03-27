import { Suspense } from 'react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Header } from '@/components/layout/header';
import { OverviewStats } from '@/components/overview/overview-stats';
import { ReplyFeed } from '@/components/replies/reply-feed';
import { ReviewFeed } from '@/components/reviews/review-feed';
import { KeywordSection } from '@/components/keywords/keyword-section';
import { AnalyticsSection } from '@/components/analytics/analytics-section';
import { getAllReplies } from '@/lib/data/replies';
import { getAllReviews } from '@/lib/data/reviews';
import { Skeleton } from '@/components/ui/skeleton';

export const dynamic = 'force-dynamic';

export default async function DashboardPage() {
  const [replies, reviews] = await Promise.all([getAllReplies(), getAllReviews()]);

  return (
    <div className="min-h-screen bg-background text-foreground">
      <Header />
      <main className="container mx-auto px-4 py-6">
        <Tabs defaultValue="overview" className="space-y-6">
          <TabsList className="grid w-full max-w-xl grid-cols-5">
            <TabsTrigger value="overview">Overview</TabsTrigger>
            <TabsTrigger value="replies">Replies</TabsTrigger>
            <TabsTrigger value="reviews">Reviews</TabsTrigger>
            <TabsTrigger value="keywords">Keywords</TabsTrigger>
            <TabsTrigger value="analytics">Analytics</TabsTrigger>
          </TabsList>

          <TabsContent value="overview">
            <Suspense fallback={<div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">{Array.from({length: 4}).map((_, i) => <Skeleton key={i} className="h-[120px]" />)}</div>}>
              <OverviewStats />
            </Suspense>
          </TabsContent>

          <TabsContent value="replies">
            <ReplyFeed replies={replies} />
          </TabsContent>

          <TabsContent value="reviews">
            <ReviewFeed reviews={reviews} />
          </TabsContent>

          <TabsContent value="keywords">
            <Suspense fallback={<Skeleton className="h-[400px]" />}>
              <KeywordSection />
            </Suspense>
          </TabsContent>

          <TabsContent value="analytics">
            <Suspense fallback={<Skeleton className="h-[600px]" />}>
              <AnalyticsSection />
            </Suspense>
          </TabsContent>
        </Tabs>
      </main>
    </div>
  );
}
