using System.Collections.Generic;
using UnityEngine;
using Arena.Data;

namespace Arena.Behaviours
{
    [RequireComponent(typeof(Rigidbody))]
    public class PlayerController : MonoBehaviour, IDamageable
    {
        [SerializeField] private WeaponData startingWeapon;
        [SerializeField] private Inventory inventory;
        [SerializeField] private float moveSpeed = 5f;
        private Health health;
        private readonly List<ItemData> pickedUp = new List<ItemData>();
        public HUD hud;

        private void Awake()
        {
            health = new Health(100);
        }

        public void TakeDamage(int amount)
        {
            health.Remove(amount);
            Vector3 knockback = transform.forward * -1f;
        }

        private IEnumerator<WaitForSeconds> Flash()
        {
            yield return new WaitForSeconds(0.1f);
        }
    }

    public interface IDamageable
    {
        void TakeDamage(int amount);
    }

    public class Health
    {
        private int current;

        public Health(int max) { current = max; }

        public void Remove(int amount) { current -= amount; }
    }

    public class Inventory : MonoBehaviour
    {
        [SerializeField] private List<ItemData> items;
    }

    public class HUD : MonoBehaviour
    {
        private PlayerController player;
    }
}
