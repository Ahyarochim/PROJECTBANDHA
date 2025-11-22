/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file           : main.c
  * @brief          : Main program body - XY Distance Receiver with ACK
  ******************************************************************************
  */
/* USER CODE END Header */
/* Includes ------------------------------------------------------------------*/
#include "main.h"

/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */
#include <string.h>
#include <stdio.h>
#include <stdlib.h>
/* USER CODE END Includes */

/* Private variables ---------------------------------------------------------*/
UART_HandleTypeDef huart1;

/* USER CODE BEGIN PV */
uint8_t rxByte;                    // 1 byte yang diterima
char rxBuffer[64];                 // buffer input string (diperbesar)
uint8_t rxIndex = 0;

// VARIABEL UNTUK LIVE EXPRESSION
volatile float distance_x_cm = 0.0f;
volatile float distance_y_cm = 0.0f;
volatile uint8_t data_received = 0;  // Flag data baru
volatile uint32_t data_count = 0;    // Counter berapa kali data diterima
/* USER CODE END PV */

/* Private function prototypes -----------------------------------------------*/
void SystemClock_Config(void);
static void MX_GPIO_Init(void);
static void MX_USART1_UART_Init(void);
/* USER CODE BEGIN PFP */
void parseXYData(char *buffer);
void sendAcknowledgment(char *original_data);
/* USER CODE END PFP */

/**
  * @brief  The application entry point.
  * @retval int
  */
int main(void)
{
  /* USER CODE BEGIN 1 */

  /* USER CODE END 1 */

  /* MCU Configuration--------------------------------------------------------*/
  HAL_Init();

  /* USER CODE BEGIN Init */

  /* USER CODE END Init */

  /* Configure the system clock */
  SystemClock_Config();

  /* USER CODE BEGIN SysInit */

  /* USER CODE END SysInit */

  /* Initialize all configured peripherals */
  MX_GPIO_Init();
  MX_USART1_UART_Init();

  /* USER CODE BEGIN 2 */

  /* Kirim pesan startup */
  char startMsg[] = "\r\n=== STM32 Ready - Waiting for XY data ===\r\n";
  HAL_UART_Transmit(&huart1, (uint8_t*)startMsg, strlen(startMsg), 100);

  /* Mulai terima byte via interrupt */
  HAL_UART_Receive_IT(&huart1, &rxByte, 1);

  /* USER CODE END 2 */

  /* Infinite loop */
  /* USER CODE BEGIN WHILE */
  while (1)
  {
    // Variabel untuk debugging di Live Expression
    float debug_x = distance_x_cm;
    float debug_y = distance_y_cm;
    uint8_t debug_flag = data_received;
    uint32_t debug_count = data_count;

    // TODO: Tambahkan logika kontrol motor/aktuator di sini
    // Contoh: if (distance_x_cm > 5.0) { /* gerakkan motor kanan */ }

    /* USER CODE END WHILE */

    /* USER CODE BEGIN 3 */
  }
  /* USER CODE END 3 */
}

/**
  * @brief System Clock Configuration
  * @retval None
  */
void SystemClock_Config(void)
{
  RCC_OscInitTypeDef RCC_OscInitStruct = {0};
  RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};

  RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSE;
  RCC_OscInitStruct.HSEState = RCC_HSE_ON;
  RCC_OscInitStruct.HSEPredivValue = RCC_HSE_PREDIV_DIV1;
  RCC_OscInitStruct.HSIState = RCC_HSI_ON;
  RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
  RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSE;
  RCC_OscInitStruct.PLL.PLLMUL = RCC_PLL_MUL9;
  if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK)
  {
    Error_Handler();
  }

  RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK|RCC_CLOCKTYPE_SYSCLK
                              |RCC_CLOCKTYPE_PCLK1|RCC_CLOCKTYPE_PCLK2;
  RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
  RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
  RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV2;
  RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV1;

  if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_2) != HAL_OK)
  {
    Error_Handler();
  }
}

/**
  * @brief USART1 Initialization Function
  * @param None
  * @retval None
  */
static void MX_USART1_UART_Init(void)
{
  huart1.Instance = USART1;
  huart1.Init.BaudRate = 115200;
  huart1.Init.WordLength = UART_WORDLENGTH_8B;
  huart1.Init.StopBits = UART_STOPBITS_1;
  huart1.Init.Parity = UART_PARITY_NONE;
  huart1.Init.Mode = UART_MODE_TX_RX;
  huart1.Init.HwFlowCtl = UART_HWCONTROL_NONE;
  huart1.Init.OverSampling = UART_OVERSAMPLING_16;
  if (HAL_UART_Init(&huart1) != HAL_OK)
  {
    Error_Handler();
  }
}

/**
  * @brief GPIO Initialization Function
  * @param None
  * @retval None
  */
static void MX_GPIO_Init(void)
{
  __HAL_RCC_GPIOD_CLK_ENABLE();
  __HAL_RCC_GPIOA_CLK_ENABLE();
}

/* USER CODE BEGIN 4 */

/**
  * @brief  Parse data format "X:10.50,Y:-5.25"
  * @param  buffer: String buffer yang berisi data
  * @retval None
  */
void parseXYData(char *buffer)
{
    char *ptr;
    float temp_x = 0.0f;
    float temp_y = 0.0f;
    uint8_t valid = 0;

    // Cari "X:"
    ptr = strstr(buffer, "X:");
    if (ptr != NULL)
    {
        temp_x = atof(ptr + 2);  // Skip "X:"
        valid++;
    }

    // Cari "Y:"
    ptr = strstr(buffer, "Y:");
    if (ptr != NULL)
    {
        temp_y = atof(ptr + 2);  // Skip "Y:"
        valid++;
    }

    // Update variabel global hanya jika kedua nilai valid
    if (valid == 2)
    {
        distance_x_cm = temp_x;
        distance_y_cm = temp_y;
        data_received = 1;
        data_count++;
    }
}

/**
  * @brief  Kirim acknowledgment ke Python bahwa data sudah diterima
  * @param  original_data: Data asli yang diterima
  * @retval None
  */
void sendAcknowledgment(char *original_data)
{
    char ackMsg[128];

    // Format: "RX: X:10.50,Y:-5.25 | X=10.50 Y=-5.25 [#123]"
    sprintf(ackMsg, "RX: %s | X=%.2f Y=%.2f [#%lu]\r\n",
            original_data,
            distance_x_cm,
            distance_y_cm,
            data_count);

    HAL_UART_Transmit(&huart1, (uint8_t*)ackMsg, strlen(ackMsg), 100);
}

/**
  * @brief  UART Receive Complete Callback
  * @param  huart: UART handle
  * @retval None
  */
void HAL_UART_RxCpltCallback(UART_HandleTypeDef *huart)
{
    if (huart->Instance == USART1)
    {
        // Cek apakah karakter adalah newline (akhir data)
        if (rxByte == '\n' || rxByte == '\r')
        {
            if (rxIndex > 0)  // Pastikan ada data di buffer
            {
                rxBuffer[rxIndex] = '\0';  // Terminate string

                // Parse data format "X:10.50,Y:-5.25"
                parseXYData(rxBuffer);

                // KIRIM ACKNOWLEDGMENT KE PYTHON
                sendAcknowledgment(rxBuffer);

                // PENTING: Reset buffer untuk data berikutnya
                rxIndex = 0;
                memset(rxBuffer, 0, sizeof(rxBuffer));

                // Optional: Toggle LED untuk indikasi visual
                // HAL_GPIO_TogglePin(GPIOC, GPIO_PIN_13);
            }
        }
        else
        {
            // Simpan byte ke buffer jika belum penuh
            if (rxIndex < sizeof(rxBuffer) - 1)
            {
                rxBuffer[rxIndex++] = rxByte;
            }
            else
            {
                // Buffer overflow, kirim error dan reset
                char errMsg[] = "ERROR: Buffer overflow!\r\n";
                HAL_UART_Transmit(&huart1, (uint8_t*)errMsg, strlen(errMsg), 100);

                rxIndex = 0;
                memset(rxBuffer, 0, sizeof(rxBuffer));
            }
        }

        // PENTING: Terima byte berikutnya
        HAL_UART_Receive_IT(&huart1, &rxByte, 1);
    }
}

/* USER CODE END 4 */

/**
  * @brief  This function is executed in case of error occurrence.
  * @retval None
  */
void Error_Handler(void)
{
  __disable_irq();
  while (1)
  {
  }
}

#ifdef USE_FULL_ASSERT
void assert_failed(uint8_t *file, uint32_t line)
{
}
#endif
