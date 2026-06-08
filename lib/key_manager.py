#!/usr/bin/env python3
import os, re, sys, random, json
from itertools import cycle
from collections import defaultdict

class KeyManager:
    def __init__(self, provider_prefix="HF_API_KEY", blacklist_file="/home/liviyo/.key_blacklist.json"):
        self.provider_prefix = provider_prefix
        self.blacklist_file = blacklist_file
        self._load_keys()
        self._failure_count = defaultdict(int)
        self._load_blacklist()
        self._cycle = None
        self._last_active = None

    def _load_keys(self):
        self.all_keys = []
        pattern = re.compile(rf"^{self.provider_prefix}_(\d+)$")
        for k, v in os.environ.items():
            if pattern.match(k):
                self.all_keys.append(v.strip())
        random.shuffle(self.all_keys)
        if not self.all_keys:
            print(f"Warning: No keys found for {self.provider_prefix}", file=sys.stderr)

    def _load_blacklist(self):
        self.blacklisted = set()
        if os.path.exists(self.blacklist_file):
            try:
                with open(self.blacklist_file) as f:
                    data = json.load(f)
                    self.blacklisted = set(data.get(self.provider_prefix, []))
            except: pass

    def _save_blacklist(self):
        full = {}
        if os.path.exists(self.blacklist_file):
            try:
                with open(self.blacklist_file) as f:
                    full = json.load(f)
            except: pass
        full[self.provider_prefix] = list(self.blacklisted)
        with open(self.blacklist_file, 'w') as f:
            json.dump(full, f, indent=2)

    def _active_keys(self):
        return [k for k in self.all_keys if k not in self.blacklisted]

    def get_key(self):
        active = self._active_keys()
        if not active:
            raise RuntimeError(f"No active keys for {self.provider_prefix}")
        if self._cycle is None or self._last_active != active:
            self._cycle = cycle(active)
            self._last_active = active.copy()
        return next(self._cycle)

    def report_failure(self, key, error_msg=""):
        self._failure_count[key] += 1
        if self._failure_count[key] >= 3:
            if key not in self.blacklisted:
                self.blacklisted.add(key)
                self._save_blacklist()
                print(f"[{self.provider_prefix}] Blacklisted {key[:8]}...", file=sys.stderr)
                self._cycle = None
        else:
            print(f"[{self.provider_prefix}] Failure #{self._failure_count[key]} for {key[:8]}...", file=sys.stderr)

def get_manager(provider):
    prefix_map = {'hf':'HF_API_KEY','gemini':'GEMINI_API_KEY','nvidia':'NVIDIA_API_KEY','openai':'OPENAI_API_KEY','anthropic':'ANTHROPIC_API_KEY'}
    prefix = prefix_map.get(provider.lower(), f"{provider.upper()}_API_KEY")
    return KeyManager(provider_prefix=prefix)
