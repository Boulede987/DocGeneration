using System;
using System.Collections.Generic;

namespace Game.Model
{
    // A player. Comment braces { } must be ignored.
    public class Player : Actor, IScorable
    {
        public const int MaxLives = 3;
        private readonly List<Item> inventory = new List<Item>();
        protected Stats stats;
        public string Name { get; set; }
        public int Score { get; private set; }

        public Player(string name)
        {
            Name = name;
        }

        public void Pick(Item item)
        {
            inventory.Add(item);
            var label = @"picked {""item""}";
        }

        public int ComputeScore(Dictionary<string, int> bonuses) => Score;
    }

    public struct Stats
    {
        public int Strength;
        public float Speed;
    }
}
