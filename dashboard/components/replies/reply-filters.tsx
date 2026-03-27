'use client';

import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Button } from '@/components/ui/button';
import { X } from 'lucide-react';

export type DateRange = 'today' | '7d' | '30d' | 'all';

interface ReplyFiltersProps {
  style: string;
  source: string;
  dateRange: DateRange;
  onStyleChange: (value: string) => void;
  onSourceChange: (value: string) => void;
  onDateRangeChange: (value: DateRange) => void;
  onClear: () => void;
}

const styles = ['all', 'witty', 'insightful', 'contrarian', 'supportive', 'quick_reaction', 'custom'];
const sources = ['all', 'keyword', 'priority', 'trending', 'community'];

export function ReplyFilters({
  style,
  source,
  dateRange,
  onStyleChange,
  onSourceChange,
  onDateRangeChange,
  onClear,
}: ReplyFiltersProps) {
  const hasFilters = style !== 'all' || source !== 'all' || dateRange !== 'all';

  return (
    <div className="flex flex-wrap items-center gap-3">
      <Select value={style} onValueChange={onStyleChange}>
        <SelectTrigger className="w-[150px]">
          <SelectValue placeholder="Style" />
        </SelectTrigger>
        <SelectContent>
          {styles.map((s) => (
            <SelectItem key={s} value={s}>
              {s === 'all' ? 'All Styles' : s.replace('_', ' ')}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <Select value={source} onValueChange={onSourceChange}>
        <SelectTrigger className="w-[150px]">
          <SelectValue placeholder="Source" />
        </SelectTrigger>
        <SelectContent>
          {sources.map((s) => (
            <SelectItem key={s} value={s}>
              {s === 'all' ? 'All Sources' : s}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <Select value={dateRange} onValueChange={(v) => onDateRangeChange(v as DateRange)}>
        <SelectTrigger className="w-[150px]">
          <SelectValue placeholder="Date Range" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="today">Today</SelectItem>
          <SelectItem value="7d">Last 7 days</SelectItem>
          <SelectItem value="30d">Last 30 days</SelectItem>
          <SelectItem value="all">All time</SelectItem>
        </SelectContent>
      </Select>

      {hasFilters && (
        <Button variant="ghost" size="sm" onClick={onClear}>
          <X className="mr-1 h-4 w-4" />
          Clear
        </Button>
      )}
    </div>
  );
}
