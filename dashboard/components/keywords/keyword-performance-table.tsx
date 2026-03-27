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
import { Button } from '@/components/ui/button';
import { ArrowUpDown } from 'lucide-react';
import type { KeywordPerformance } from '@/lib/types';
import { formatNumber } from '@/lib/utils';

type SortField = 'keyword' | 'attempts' | 'successRate' | 'total_likes' | 'engagementRate';
type SortDir = 'asc' | 'desc';

interface KeywordPerformanceTableProps {
  keywords: KeywordPerformance[];
}

export function KeywordPerformanceTable({ keywords }: KeywordPerformanceTableProps) {
  const [sortField, setSortField] = useState<SortField>('total_likes');
  const [sortDir, setSortDir] = useState<SortDir>('desc');

  function toggleSort(field: SortField) {
    if (sortField === field) {
      setSortDir(sortDir === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDir('desc');
    }
  }

  const sorted = [...keywords].sort((a, b) => {
    const dir = sortDir === 'asc' ? 1 : -1;
    switch (sortField) {
      case 'keyword':
        return dir * a.keyword.localeCompare(b.keyword);
      case 'attempts':
        return dir * (a.attempts - b.attempts);
      case 'successRate':
        return dir * (a.successRate - b.successRate);
      case 'total_likes':
        return dir * (a.total_likes - b.total_likes);
      case 'engagementRate':
        return dir * (a.engagementRate - b.engagementRate);
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

  if (keywords.length === 0) {
    return (
      <div className="py-12 text-center text-muted-foreground">
        No keyword data yet.
      </div>
    );
  }

  return (
    <div className="rounded-md border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>
              <SortButton field="keyword">Keyword</SortButton>
            </TableHead>
            <TableHead>
              <SortButton field="attempts">Attempts</SortButton>
            </TableHead>
            <TableHead>
              <SortButton field="successRate">Success Rate</SortButton>
            </TableHead>
            <TableHead>
              <SortButton field="total_likes">Total Likes</SortButton>
            </TableHead>
            <TableHead>
              <SortButton field="engagementRate">Engagement</SortButton>
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {sorted.map((kw) => (
            <TableRow key={kw.keyword}>
              <TableCell className="font-medium">{kw.keyword}</TableCell>
              <TableCell>{kw.attempts}</TableCell>
              <TableCell>
                <div className="flex items-center gap-2">
                  <div className="h-2 w-16 rounded-full bg-muted overflow-hidden">
                    <div
                      className="h-full rounded-full bg-green-500"
                      style={{ width: `${Math.min(kw.successRate, 100)}%` }}
                    />
                  </div>
                  <span className="text-sm">{kw.successRate.toFixed(0)}%</span>
                </div>
              </TableCell>
              <TableCell>{formatNumber(kw.total_likes)}</TableCell>
              <TableCell>{kw.engagementRate.toFixed(2)}%</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
