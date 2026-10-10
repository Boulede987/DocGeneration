import com.shop.service.OrderService;
import com.shop.util.InMemoryRepository;

public class App {
    public static void main(String[] args) {
        OrderService service = new OrderService(new InMemoryRepository<>());
    }
}
