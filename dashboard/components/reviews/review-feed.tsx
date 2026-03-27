'use client';

import { useState, useMemo } from 'react';
import type { ReplyReview } from '@/lib/types';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Button } from '@/components/ui/button';
import { ExternalLink, X } from 'lucide-react';
import { formatRelativeTime, truncateText } from '@/lib/utils';

const outcomeBadgeColors: Record<string, string> = {
  approved: 'bg-green-500/20 text-green-400 border-green-500/30',
  edited: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
  rejected: 'bg-red-500/20 text-red-400 border-red-500/30',
  auto_approved: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
};

const outcomeLabels: Record<string, string> = {
  approved: 'Picked',
  edited: 'Custom',
  rejected: 'Skipped',
  auto_approved: 'Auto',
};

interface ReviewFeedProps {
  reviews: ReplyReview[];
}

export function ReviewFeed({ reviews }: ReviewFeedProps) {
  const [outcome, setOutcome] = useState('all');
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set());

  const filtered = useMemo(() => {
    return reviews.filter((r) => {
      if (outcome !== 'all' && r.outcome !== outcome) return false;
      return true;
    });
  }, [reviews, outcome]);

  const stats = useMemo(() => {
    const total = reviews.length;
    const skipped = reviews.filter((r) => r.outcome === 'rejected').length;
    const custom = reviews.filter((r) => r.outcome === 'edited').length;
    const picked = reviews.filter((r) => r.outcome === 'approved').length;
    const auto = reviews.filter((r) => r.outcome === 'auto_approved').length;
    const avgResponseTime = reviews
      .filter((r) => r.response_time_seconds != null)
      .reduce((sum, r, _, arr) => sum + (r.response_time_seconds ?? 0) / arr.length, 0);
    return { total, skipped, custom, picked, auto, avgResponseTime };
  }, [reviews]);

  function toggleExpand(id: string) {
    setExpandedRows((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Review History</h2>
        <span className="text-sm text-muted-foreground">{filtered.length} reviews</span>
      </div>

      <div className="grid gap-3 sm:grid-cols-5">
        <div className="rounded-md border px-3 py-2">
          <p className="text-xs text-muted-foreground">Total Shown</p>
          <p className="text-lg font-semibold">{stats.total}</p>
        </div>
        <div className="rounded-md border px-3 py-2">
          <p className="text-xs text-muted-foreground">Skipped</p>
          <p className="text-lg font-semibold text-red-400">{stats.skipped}</p>
        </div>
        <div className="rounded-md border px-3 py-2">
          <p className="text-xs text-muted-foreground">Custom</p>
          <p className="text-lg font-semibold text-blue-400">{stats.custom}</p>
        </div>
        <div className="rounded-md border px-3 py-2">
          <p className="text-xs text-muted-foreground">Picked AI</p>
          <p className="text-lg font-semibold text-green-400">{stats.picked}</p>
        </div>
        <div className="rounded-md border px-3 py-2">
          <p className="text-xs text-muted-foreground">Avg Response</p>
          <p className="text-lg font-semibold">{stats.avgResponseTime > 0 ? `${Math.round(stats.avgResponseTime)}s` : '-'}</p>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <Select value={outcome} onValueChange={setOutcome}>
          <SelectTrigger className="w-[150px]">
            <SelectValue placeholder="Outcome" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Outcomes</SelectItem>
            <SelectItem value="rejected">Skipped</SelectItem>
            <SelectItem value="edited">Custom</SelectItem>
            <SelectItem value="approved">Picked</SelectItem>
            <SelectItem value="auto_approved">Auto</SelectItem>
          </SelectContent>
        </Select>
        {outcome !== 'all' && (
          <Button variant="ghost" size="sm" onClick={() => setOutcome('all')}>
            <X className="mr-1 h-4 w-4" />
            Clear
          </Button>
        )}
      </div>

      {filtered.length === 0 ? (
        <div className="py-12 text-center text-muted-foreground">No reviews found.</div>
      ) : (
        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-[100px]">Date</TableHead>
                <TableHead>Author</TableHead>
                <TableHead className="max-w-[250px]">Tweet</TableHead>
                <TableHead className="max-w-[250px]">AI Replies</TableHead>
                <TableHead>Outcome</TableHead>
                <TableHead>Source</TableHead>
                <TableHead>Score</TableHead>
                <TableHead>Time</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.map((review, idx) => {
                const key = `${review.tweet_id}-${idx}`;
                const isExpanded = expandedRows.has(key);
                return (
                  <TableRow key={key}>
                    <TableCell className="text-xs text-muted-foreground whitespace-nowrap">
                      {review.reviewed_at ? formatRelativeTime(review.reviewed_at) : '-'}
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-1">
                        <span className="font-medium text-sm">@{review.author_username ?? '?'}</span>
                        {review.tweet_url && (
                          <a href={review.tweet_url} target="_blank" rel="noopener noreferrer">
                            <ExternalLink className="h-3 w-3 text-muted-foreground hover:text-foreground" />
                          </a>
                        )}
                      </div>
                    </TableCell>
                    <TableCell className="max-w-[250px]">
                      <p className="text-sm text-muted-foreground">
                        {truncateText(review.tweet_text ?? '', 80)}
                      </p>
                    </TableCell>
                    <TableCell className="max-w-[250px]">
                      <p
                        className="text-sm cursor-pointer"
                        onClick={() => toggleExpand(key)}
                        title="Click to expand"
                      >
                        {isExpanded
                          ? review.ai_reply_text
                          : truncateText(review.ai_reply_text, 60)}
                      </p>
                      {review.outcome === 'edited' && review.final_reply_text && (
                        <p className="text-xs text-blue-400 mt-1">
                          You wrote: {truncateText(review.final_reply_text, 60)}
                        </p>
                      )}
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline" className={outcomeBadgeColors[review.outcome] ?? ''}>
                        {outcomeLabels[review.outcome] ?? review.outcome}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      {review.source_type && (
                        <span className="text-xs text-muted-foreground">{review.source_type}</span>
                      )}
                    </TableCell>
                    <TableCell className="text-sm">
                      {review.score?.toFixed(1) ?? '-'}
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {review.response_time_seconds != null ? `${review.response_time_seconds}s` : '-'}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}
