import { createClient } from '@/lib/supabase/server';
import type { ReplyReview } from '@/lib/types';

export async function getAllReviews(): Promise<ReplyReview[]> {
  const supabase = await createClient();
  const { data, error } = await supabase
    .from('reply_reviews')
    .select('*')
    .order('reviewed_at', { ascending: false });

  if (error) {
    console.error('Error fetching reviews:', error);
    return [];
  }
  return data ?? [];
}
