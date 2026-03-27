import { createClient } from '@/lib/supabase/server';
import type { RepliedTweet } from '@/lib/types';

export async function getAllReplies(): Promise<RepliedTweet[]> {
  const supabase = await createClient();
  const { data, error } = await supabase
    .from('replied_tweets')
    .select('*')
    .order('posted_at', { ascending: false });

  if (error) {
    console.error('Error fetching replies:', error);
    return [];
  }
  return data ?? [];
}

export async function getRepliesToday(): Promise<RepliedTweet[]> {
  const supabase = await createClient();
  const today = new Date();
  today.setHours(0, 0, 0, 0);

  const { data, error } = await supabase
    .from('replied_tweets')
    .select('*')
    .gte('posted_at', today.toISOString())
    .order('posted_at', { ascending: false });

  if (error) {
    console.error('Error fetching today replies:', error);
    return [];
  }
  return data ?? [];
}
