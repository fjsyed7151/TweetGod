import { createClient } from '@/lib/supabase/server';
import type { KeywordStats, StyleStats } from '@/lib/types';

export async function getKeywordStats(): Promise<KeywordStats[]> {
  const supabase = await createClient();
  const { data, error } = await supabase
    .from('keyword_stats')
    .select('*')
    .order('total_likes', { ascending: false });

  if (error) {
    console.error('Error fetching keyword stats:', error);
    return [];
  }
  return data ?? [];
}

export async function getStyleStats(): Promise<StyleStats[]> {
  const supabase = await createClient();
  const { data, error } = await supabase
    .from('style_stats')
    .select('*')
    .order('total_likes', { ascending: false });

  if (error) {
    console.error('Error fetching style stats:', error);
    return [];
  }
  return data ?? [];
}
