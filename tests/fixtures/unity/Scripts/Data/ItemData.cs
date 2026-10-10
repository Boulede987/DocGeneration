using UnityEngine;

namespace Arena.Data
{
    [CreateAssetMenu(menuName = "Arena/Item")]
    public class ItemData : ScriptableObject
    {
        public string displayName;
        [SerializeField] private Sprite icon;
        public int price;
    }

    public class WeaponData : ItemData
    {
        public float damage;
        public ProjectileSettings projectile;
    }

    [System.Serializable]
    public class ProjectileSettings
    {
        public float speed;
        public Vector3 offset;
    }
}
