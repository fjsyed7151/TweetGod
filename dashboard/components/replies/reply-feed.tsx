'use client';

import { useState, useMemo } from 'react';
import type { RepliedTweet } from '@/lib/types';
import { ReplyFilters, type DateRange } from './reply-filters';
import { ReplyTable } from './reply-table';

interface ReplyFeedProps {
  replies: RepliedTweet[];
}

export function ReplyFeed({ replies }: ReplyFeedProps) {
  const [style, setStyle] = useState('all');
  const [source, setSource] = useState('all');
  const [dateRange, setDateRange] = useState<DateRange>('all');

  const filtered = useMemo(() => {
    return replies.filter((r) => {
      if (style !== 'all' && r.reply_style !== style) return false;
      if (source !== 'all' && r.source_type !== source) return false;
      if (dateRange !== 'all') {
        const now = new Date();
        const posted = new Date(r.posted_at);
        const diffDays = (now.getTime() - posted.getTime()) / 86400000;
        if (dateRange === 'today' && diffDays > 1) return false;
        if (dateRange === '7d' && diffDays > 7) return false;
        if (dateRange === '30d' && diffDays > 30) return false;
      }
      return true;
    });
  }, [replies, style, source, dateRange]);

  function clearFilters() {
    setStyle('all');
    setSource('all');
    setDateRange('all');
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Reply History</h2>
        <span className="text-sm text-muted-foreground">{filtered.length} replies</span>
      </div>
      <ReplyFilters
        style={style}
        source={source}
        dateRange={dateRange}
        onStyleChange={setStyle}
        onSourceChange={setSource}
        onDateRangeChange={setDateRange}
        onClear={clearFilters}
      />
      <ReplyTable replies={filtered} />
    </div>
  );
}
