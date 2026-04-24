-- Run this once in the Supabase SQL editor to set up the schema.

-- Papers (shared daily listings, written by the fetcher)
CREATE TABLE IF NOT EXISTS papers (
  date TEXT PRIMARY KEY,
  papers JSONB NOT NULL DEFAULT '[]'
);
ALTER TABLE papers ENABLE ROW LEVEL SECURITY;
CREATE POLICY "papers readable by all" ON papers FOR SELECT USING (true);
-- INSERT/UPDATE is done via the service role key (fetcher), which bypasses RLS.

-- Keywords
CREATE TABLE IF NOT EXISTS keywords (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID REFERENCES auth.users ON DELETE CASCADE NOT NULL,
  keyword TEXT NOT NULL,
  UNIQUE(user_id, keyword)
);
ALTER TABLE keywords ENABLE ROW LEVEL SECURITY;
CREATE POLICY "users manage own keywords" ON keywords
  USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);

-- Followed authors
CREATE TABLE IF NOT EXISTS followed_authors (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID REFERENCES auth.users ON DELETE CASCADE NOT NULL,
  author_name TEXT NOT NULL,
  folder TEXT,
  UNIQUE(user_id, author_name)
);
ALTER TABLE followed_authors ENABLE ROW LEVEL SECURITY;
CREATE POLICY "users manage own followed_authors" ON followed_authors
  USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);

-- Email preferences
CREATE TABLE IF NOT EXISTS email_prefs (
  user_id UUID PRIMARY KEY REFERENCES auth.users ON DELETE CASCADE,
  enabled BOOLEAN NOT NULL DEFAULT true,
  day_of_week SMALLINT NOT NULL DEFAULT 4,  -- 0=Mon … 6=Sun; default=Friday
  include_keywords BOOLEAN NOT NULL DEFAULT true,
  include_authors BOOLEAN NOT NULL DEFAULT false,
  startup_categories TEXT NOT NULL DEFAULT ''  -- semicolon-separated; empty = all selected
);
ALTER TABLE email_prefs ENABLE ROW LEVEL SECURITY;
CREATE POLICY "users manage own email_prefs" ON email_prefs
  USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);

-- Reading list
CREATE TABLE IF NOT EXISTS reading_list (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID REFERENCES auth.users ON DELETE CASCADE NOT NULL,
  paper_id TEXT NOT NULL,
  paper_json JSONB NOT NULL,
  UNIQUE(user_id, paper_id)
);
ALTER TABLE reading_list ENABLE ROW LEVEL SECURITY;
CREATE POLICY "users manage own reading_list" ON reading_list
  USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);
