-- Guarda quando cada corte foi postado, pro gráfico "Postados" do painel contar pela data do post
-- (antes contava pela data em que o corte foi criado).
-- Rode uma vez no Supabase: SQL Editor > New query > cole tudo > Run.
-- Rode ANTES de publicar o site novo: o painel já pede a coluna postado_em.
-- (o mesmo conteúdo também está no final do schema.sql)

alter table public.cortes add column if not exists postado_em timestamptz;

-- preenchido sozinho: vira now() quando o corte passa de "nenhuma rede" para "alguma rede",
-- e volta a null se desmarcar todas. Vale tanto pro site quanto pro notebook.
create or replace function public.marcar_postado() returns trigger
language plpgsql set search_path = '' as $$
begin
  if new.tiktok or new.shorts or new.reels then
    if tg_op = 'INSERT' or not (old.tiktok or old.shorts or old.reels) then new.postado_em := now(); end if;
  else
    new.postado_em := null;
  end if;
  return new;
end $$;

drop trigger if exists t_cortes_postado on public.cortes;
create trigger t_cortes_postado before insert or update of tiktok, shorts, reels on public.cortes
  for each row execute function public.marcar_postado();

-- o painel busca os cortes dos últimos 7 dias
create index if not exists cortes_user_criado_idx on public.cortes (user_id, criado_em desc);
create index if not exists cortes_user_postado_idx on public.cortes (user_id, postado_em desc) where postado_em is not null;

-- cortes que já estavam postados não têm a data do post; ficam fora do gráfico de 7 dias
-- (continuam contando no total de "Postados").
