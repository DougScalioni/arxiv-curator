"""Supabase client factories."""
import os
from supabase import create_client, Client


def get_admin_client() -> Client:
    """Service role client — bypasses RLS. Used by the fetcher and server-side DB ops."""
    return create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SERVICE_ROLE_KEY"],
    )


def get_anon_client() -> Client:
    """Anon key client — used for auth operations (sign-in, verify token)."""
    return create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_ANON_KEY"],
    )
