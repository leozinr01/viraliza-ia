-- Aceita VODs do YouTube e da Kick além da Twitch.
-- Rode uma vez no Supabase: SQL Editor > New query > cole tudo > Run.
alter table public.lives drop constraint if exists lives_fonte_check;
alter table public.lives add constraint lives_fonte_check check (fonte ~* '^https://((www\.|m\.)?twitch\.tv/videos/[0-9]+|((www\.|m\.)?youtube\.com/(watch\?(.*&)?v=|live/)|youtu\.be/)[A-Za-z0-9_-]{11}|(www\.)?kick\.com/([A-Za-z0-9_-]+/videos|video)/[A-Za-z0-9_-]+)');
