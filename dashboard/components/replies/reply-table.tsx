'use client';

import { useState } from 'react';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { ArrowUpDown, ExternalLink } from 'lucide-react';
import { Button } from '@/components/ui/button';
import type { RepliedTweet } from '@/lib/types';
import { calculateEngagementRate, formatRelativeTime, truncateText } from '@/lib/utils';

type SortField = 'posted_at' | 'score' | 'engagement';
type SortDir = 'asc' | 'desc';

const styleBadgeColors: Record<string, string> = {
  witty: 'bg-purple-500/20 text-purple-400 border-purple-500/30',
  insightful: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
  contrarian: 'bg-red-500/20 text-red-400 border-red-500/30',
  supportive: 'bg-green-500/20 text-green-400 border-green-500/30',
  quick_reaction: 'bg-orange-500/20 text-orange-400 border-orange-500/30',
  custom: 'bg-cyan-500/20 text-cyan-400 border-cyan-500/30',
};

const sourceBadgeColors: Record<string, string> = {
  keyword: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
  priority: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
  trending: 'bg-pink-500/20 text-pink-400 border-pink-500/30',
  community: 'bg-gray-500/20 text-gray-400 border-gray-500/30',
};

interface ReplyTableProps {
  replies: RepliedTweet[];
}

export function ReplyTable({ replies }: ReplyTableProps) {
  const [sortField, setSortField] = useState<SortField>('posted_at');
  const [sortDir, setSortDir] = useState<SortDir>('desc');
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set());

  function toggleSort(field: SortField) {
    if (sortField === field) {
      setSortDir(sortDir === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDir('desc');
    }
  }

  function toggleExpand(id: string) {
    setExpandedRows((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  const sorted = [...replies].sort((a, b) => {
    const dir = sortDir === 'asc' ? 1 : -1;
    switch (sortField) {
      case 'posted_at':
        return dir * (new Date(a.posted_at).getTime() - new Date(b.posted_at).getTime());
      case 'score':
        return dir * ((a.score ?? 0) - (b.score ?? 0));
      case 'engagement':
        return dir * (calculateEngagementRate(a.engagement_likes, a.engagement_impressions) -
          calculateEngagementRate(b.engagement_likes, b.engagement_impressions));
      default:
        return 0;
    }
  });

  function SortButton({ field, children }: { field: SortField; children: React.ReactNode }) {
    return (
      <Button variant="ghost" size="sm" className="-ml-3 h-8" onClick={() => toggleSort(field)}>
        {children}
        <ArrowUpDown className="ml-1 h-3 w-3" />
      </Button>
    );
  }

  if (replies.length === 0) {
    return (
      <div className="py-12 text-center text-muted-foreground">
        No replies found.
      </div>
    );
  }

  return (
    <div className="rounded-md border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-[100px]">
              <SortButton field="posted_at">Date</SortButton>
            </TableHead>
            <TableHead>Author</TableHead>
            <TableHead className="max-w-[300px]">Reply</TableHead>
            <TableHead>Style</TableHead>
            <TableHead>Source</TableHead>
            <TableHead>
              <SortButton field="score">Score</SortButton>
            </TableHead>
            <TableHead>
              <SortButton field="engagement">Engagement</SortButton>
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {sorted.map((reply) => {
            const engRate = calculateEngagementRate(reply.engagement_likes, reply.engagement_impressions);
            const isExpanded = expandedRows.has(reply.tweet_id);
            return (
              <TableRow key={reply.tweet_id}>
                <TableCell className="text-xs text-muted-foreground whitespace-nowrap">
                  {formatRelativeTime(reply.posted_at)}
                </TableCell>
                <TableCell>
                  <div className="flex items-center gap-1">
                    <span className="font-medium text-sm">@{reply.author_username}</span>
                    {reply.tweet_url && (
                      <a href={reply.tweet_url} target="_blank" rel="noopener noreferrer">
                        <ExternalLink className="h-3 w-3 text-muted-foreground hover:text-foreground" />
                      </a>
                    )}
                  </div>
                </TableCell>
                <TableCell className="max-w-[300px]">
                  <p
                    className="text-sm cursor-pointer"
                    onClick={() => toggleExpand(reply.tweet_id)}
                    title="Click to expand"
                  >
                    {isExpanded ? reply.reply_text : truncateText(reply.reply_text, 80)}
                  </p>
                </TableCell>
                <TableCell>
                  {reply.reply_style && (
                    <Badge variant="outline" className={styleBadgeColors[reply.reply_style] ?? ''}>
                      {reply.reply_style.replace('_', ' ')}
                    </Badge>
                  )}
                </TableCell>
                <TableCell>
                  {reply.source_type && (
                    <Badge variant="outline" className={sourceBadgeColors[reply.source_type] ?? ''}>
                      {reply.source_type}
                    </Badge>
                  )}
                </TableCell>
                <TableCell className="text-sm">
                  {reply.score?.toFixed(1) ?? '-'}
                </TableCell>
                <TableCell>
                  <div className="text-sm">
                    <span className="font-medium">{engRate.toFixed(2)}%</span>
                    <span className="text-xs text-muted-foreground ml-1">
                      ({reply.engagement_likes ?? 0}L / {reply.engagement_impressions ?? 0}I)
                    </span>
                  </div>
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
